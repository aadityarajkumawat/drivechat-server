import io
from typing import List

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from llama_index.readers.base import BaseReader
from llama_index.readers.schema.base import Document
from PyPDF2 import PdfReader
from utils import GOOGLE_CLIENT_SECRET, GOOGLE_CLIENT_ID
import pandas as pd

# If modifying these scopes, delete the file token.json.
SCOPES = [
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

FOLDER_DEPTH_THRESHOLD = 10


class GoogleDrive(BaseReader):
    """
    Google Drive reader.
    Reads files from Google Drive, take in a folder url and read all the files in the folder upto a depth of 5.
    """

    def __init__(self, token: str, refresh: str):
        self.token = token
        self.refresh = refresh

    def load_data(self, drive_url: str) -> List[Document]:
        credentials = Credentials(
            token=self.token,
            refresh_token=self.refresh,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
        )
        documents = []

        try:
            folder_id = self.get_folder_id_from_url(drive_url)
            service = build("drive", "v3", credentials=credentials)

            files = self.get_files_in_folder(service, folder_id)

            for file in files:
                print("Reading", file["name"])
                contents = self.read_file(service, file)
                print(file["name"], "DONE")
                documents.append(Document(text=contents))
        except Exception as e:
            raise Exception("Can't load data from Google Drive" + str(e))

        return documents

    def get_folder_id_from_url(self, drive_url: str):
        return drive_url[
            drive_url.find("/folders/") + len("/folders/") : drive_url.find("?")
        ].strip()

    def is_folder(self, item):
        return item.get("webViewLink").count("folder") > 0

    def get_files_in_folder(self, service, folder_id: str, depth: int = 0):
        # print(f"Getting files in folder {folder_id} at depth {depth}")
        if depth > FOLDER_DEPTH_THRESHOLD:
            return []

        # Call the Drive v3 API
        results = (
            service.files()
            .list(
                pageSize=40,
                fields="nextPageToken, files(id, name, webViewLink, mimeType)",
                q="'{0}' in parents".format(folder_id),
            )
            .execute()
        )
        items: list = results.get("files", [])

        files = []

        # Reached an empty folder
        if not items:
            print("No files found.")
            return files

        # Here are all the files in this folder_id
        for item in items:
            # print(u'Name: {0}\nID: {1}\nWebViewLink: {2}\n'.format(item['name'], item['id'], item.get('webViewLink')))

            if self.is_folder(item):
                files.extend(self.get_files_in_folder(service, item["id"], depth + 1))
            else:
                files.append(item)

        return files

    def read_text_file_content(self, service, file):
        download_file_request = service.files().get_media(fileId=file["id"])

        try:
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, download_file_request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                print("Download %d%%." % int(status.progress() * 100))

            fh.seek(0)
            file_data = fh.getvalue().decode("utf-8")
            return file_data
        except Exception as error:
            print(f"An error occurred: {error}")

    def read_doc_file_content(self, service, file):
        download_file_request = service.files().export_media(
            fileId=file["id"], mimeType="text/plain"
        )

        try:
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, download_file_request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                print("Download %d%%." % int(status.progress() * 100))

            fh.seek(0)
            file_data = fh.getvalue().decode("utf-8")
            return file_data
        except Exception as error:
            print(f"An error occurred: {error}")

    def read_pdf_file_content(self, service, file):
        download_file_request = service.files().get_media(fileId=file["id"])

        try:
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, download_file_request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                print("Download %d%%." % int(status.progress() * 100))

            fh.seek(0)
            pdf = PdfReader(fh)
            contents = ""

            for page in range(len(pdf.pages)):
                contents += pdf.pages[page].extract_text()

            return contents
        except Exception as error:
            print(f"An error occurred: {error}")

    def read_google_sheet(self, service, spreadsheet_id: str, range_name: str):
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
        )
        rows = result.get("values", [])
        return rows

    def read_excel_file_content(self, service, file_id):
        content = ""
        request = service.files().get_media(fileId=file_id)
        downloaded_file = io.BytesIO()
        downloader = MediaIoBaseDownload(downloaded_file, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print("Download %d%%." % int(status.progress() * 100))
        downloaded_file.seek(0)

        data = pd.read_excel(downloaded_file)

        def stringify_data_frame(file: pd.DataFrame) -> str:
            contents = ""
            for cols in file.columns:
                contents += cols + ", "
            contents += "\n"
            for row in file.iloc:
                for value in row.values:
                    contents += str(value) + ", "
                contents += "\n"
            return contents

        content = stringify_data_frame(data)

        return content

    def read_file(self, service, file):
        if file["mimeType"] == "application/vnd.google-apps.document":
            return self.read_doc_file_content(service, file)
        elif file["mimeType"] == "text/plain":
            return self.read_text_file_content(service, file)
        elif file["mimeType"] == "application/pdf":
            return self.read_pdf_file_content(service, file)
        elif file["mimeType"] == "application/vnd.google-apps.spreadsheet":
            spreadsheet_id = file["id"]
            range_name = "A1:ZZZ1000"
            print("file", file)
            return self.read_google_sheet(service, spreadsheet_id, range_name)
        elif (
            file["mimeType"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ):
            return self.read_excel_file_content(service, file["id"])
        else:
            return ""
