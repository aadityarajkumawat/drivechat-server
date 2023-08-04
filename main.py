from flask import Flask, request, render_template, Response
from flask_cors import CORS
from llama_index.readers import Document
import requests
import urllib.parse
from utils import REDIRECT_URI, GOOGLE_CLIENT_SECRET, GOOGLE_CLIENT_ID
from jwt import decode, encode, ExpiredSignatureError
from models.main import *
import datetime
from connector.gdrive import GoogleDrive
from llama_index import (
    VectorStoreIndex,
    ServiceContext,
    set_global_service_context,
    StorageContext,
    load_index_from_storage,
)
from llama_index.llms import OpenAI


app = Flask(__name__)
cors = CORS(app, origins="*", allow_headers=["Content-Type", "Authorization"])

init()

SECRET = "efqwetoug4ofibvewfoibevwfioew"
TOKEN_EXPIRY = 240


def token_to_user(token: str):
    try:
        data = decode(
            token,
            algorithms=["HS256"],
            key=SECRET,
            options={"verify_signature": False, "verify_exp": True},
        )
        return data
    except ExpiredSignatureError:
        return None


@app.route("/")
def hello_world():
    return "Hello, World!"


@app.route("/chat", methods=["POST"])
def chat():
    try:
        body = request.json
        query = body["query"]
        auth_header = request.headers.get("Authorization", default="")
        user = token_to_user(auth_header)

        if user is None:
            return "User not found"

        # load index from directory
        user_id = user["user_id"]

        # rebuild storage context
        storage_context = StorageContext.from_defaults(
            persist_dir=f"indices/index-{user_id}"
        )

        # load index
        index = load_index_from_storage(storage_context)

        query_engine = index.as_query_engine(streaming=True)
        response = query_engine.query(query)

        def tokens():
            for tk in response.response_gen:
                yield tk

        # return {"response": response.__str__()}
        return Response(tokens(), mimetype="text/event-stream")
    except Exception as e:
        print(e)
        return "Error"


@app.route("/callback/google")
def google_callback():
    try:
        args = request.args
        redirect_uri = args.get("redirect_uri", default="")
        code = args.get("code", default="")

        url = "https://oauth2.googleapis.com/token"

        values = {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": f"{REDIRECT_URI}?redirect_uri={redirect_uri}"
            if redirect_uri != ""
            else REDIRECT_URI,
            "grant_type": "authorization_code",
        }

        qs = urllib.parse.urlencode(values)

        token_res = requests.post(
            f"{url}?{qs}", headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        data = token_res.json()

        print(data)

        id_token = data["id_token"]
        access_token = data["access_token"]
        refresh_token = data["refresh_token"]

        token_data = decode(id_token, options={"verify_signature": False})

        email = token_data["email"]
        name = token_data["name"]
        picture = token_data["picture"]

        # check if user already exists
        user = User.get_or_none(User.email == email)

        if not user:
            user = User.create(email=email, name=name, picture=picture)
            token = encode(
                payload={
                    "user_id": user.id,
                    "exp": datetime.datetime.utcnow()
                    + datetime.timedelta(hours=TOKEN_EXPIRY),
                },
                algorithm="HS256",
                key=SECRET,
            )
            session = Session.create(
                user=user,
                token=token,
                refresh_token=refresh_token,
                access_token=access_token,
            )
            return render_template("auth-success.html", token=session.token)
        else:
            # check if session exists
            session = Session.get_or_none(Session.user == user)

            # if not create a new session
            if not session:
                token = encode({"user_id": user.id}, SECRET)
                session = Session.create(
                    user=user,
                    token=token,
                    refresh_token=refresh_token,
                    access_token=access_token,
                )
                return render_template("auth-success.html", token=token)
            # else check if the exising session is valid
            else:
                decode(
                    session.token,
                    algorithms=["HS256"],
                    key=SECRET,
                    options={"verify_signature": False, "verify_exp": True},
                )
                return render_template("auth-success.html", token=session.token)
    except ExpiredSignatureError:
        new_token = encode(
            payload={
                "user_id": user.id,
                "exp": datetime.datetime.utcnow()
                + datetime.timedelta(hours=TOKEN_EXPIRY),
            },
            algorithm="HS256",
            key=SECRET,
        )
        Session.update(token=new_token).where(Session.user == user).execute()
        return render_template("auth-success.html", token=new_token)
    except Exception as e:
        print("error", e)
        return "Error"


@app.route("/index-gdrive", methods=["POST"])
def index_gdrive():
    json = request.json
    drive_url = json["drive_url"]
    name = json["name"] if "name" in json else "G-Drive Folder"

    headers = request.headers
    auth_header = headers.get("Authorization", default="")

    user = token_to_user(auth_header)
    user_id = user["user_id"]

    user = User.get_or_none(User.id == user_id)
    session = Session.get_or_none(Session.user == user)

    try:
        # use the GoogleDrive connector to load documents
        gdrive = GoogleDrive(session.access_token, session.refresh_token)
        docs = gdrive.load_data(drive_url)

        # configure llm
        llm = OpenAI(model="gpt-3.5-turbo", temperature=0, max_tokens=256)

        # configure service context
        service_context = ServiceContext.from_defaults(llm=llm)
        set_global_service_context(service_context)

        # build index from documents
        index = VectorStoreIndex.from_documents(docs)

        # save index to file system
        index.storage_context.persist(persist_dir=f"indices/index-{user.id}")

        # delete existing indices
        Index.delete().where(Index.user == user).execute()
        # save index to database
        Index.create(
            user=user,
            link=drive_url,
            name=name,
        )

        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.route("/indexed")
def indexed():
    try:
        index_found = False
        index_in_db = False
        headers = request.headers
        auth_header = headers.get("Authorization", default="")

        user = token_to_user(auth_header)
        user_id = user["user_id"]

        user = User.get_or_none(User.id == user_id)

        StorageContext.from_defaults(persist_dir=f"indices/index-{user.id}")
        index_found = True

        index = Index.get_or_none(Index.user == user)
        if index is not None and index.link != "":
            index_in_db = True

        indexed = index_found and index_in_db

        return {"indexed": indexed, "indexLink": index.link, "indexName": index.name}
    except Exception as e:
        print(e)
        return {"indexed": False}


if __name__ == "__main__":
    app.run(port=5000, debug=True, host="0.0.0.0")
