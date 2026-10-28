"""
Запуск:
    pip install flask youtube-transcript-api
    python app.py
и открыть http://127.0.0.1:8765
"""
import re
import webbrowser
from threading import Timer

from flask import Flask, jsonify, request, send_from_directory
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

app = Flask(__name__, static_folder="static", static_url_path="")
api = YouTubeTranscriptApi()

ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
URL_PATTERNS = [
    r"(?:v=|vi=)([A-Za-z0-9_-]{11})",
    r"youtu\.be/([A-Za-z0-9_-]{11})",
    r"/(?:embed|shorts|live|v)/([A-Za-z0-9_-]{11})"
]


def extract_video_id(url: str):
    url = (url or "").strip()
    if ID_RE.match(url):
        return url
    for p in URL_PATTERNS:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def error(msg: str, code: int = 400):
    return jsonify({"error": msg}), code


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/languages")
def languages():
    vid = extract_video_id(request.args.get("url", ""))
    if not vid:
        return error("Не понял ссылку. Нужна ссылка на видео YouTube или его ID.")
    try:
        tl = api.list(vid)
    except TranscriptsDisabled:
        return error("У этого видео субтитры отключены.", 404)
    except VideoUnavailable:
        return error("Видео недоступно (удалено, приватное или с ограничением).", 404)
    except CouldNotRetrieveTranscript as e:
        return error(f"YouTube не отдал субтитры: {type(e).__name__}", 502)

    tracks = []
    translatable_to = {}
    for t in tl:
        tracks.append({
            "code": t.language_code,
            "name": t.language,
            "auto": t.is_generated,
            "translatable": t.is_translatable,
        })
        for tr in t.translation_languages:
            translatable_to[tr.language_code] = tr.language
    tracks.sort(key=lambda x: x["auto"])
    return jsonify({
        "videoId": vid,
        "tracks": tracks,
        "translations": [{"code": c, "name": n} for c, n in sorted(translatable_to.items(), key=lambda x: x[1])],
    })


@app.get("/api/transcript")
def transcript():
    vid = extract_video_id(request.args.get("url", ""))
    if not vid:
        return error("Не понял ссылку.")
    lang = request.args.get("lang")
    auto = request.args.get("auto") == "1"
    translate_to = request.args.get("translate")

    try:
        tl = api.list(vid)
        track = None
        if lang:
            pool = [t for t in tl if t.language_code == lang and t.is_generated == auto]
            track = pool[0] if pool else None
        if track is None:
            try:
                track = tl.find_manually_created_transcript(["ru", "en"])
            except NoTranscriptFound:
                track = next(iter(tl))
        if translate_to and translate_to != track.language_code:
            track = track.translate(translate_to)
        fetched = track.fetch()
    except TranscriptsDisabled:
        return error("У этого видео субтитры отключены.", 404)
    except VideoUnavailable:
        return error("Видео недоступно.", 404)
    except CouldNotRetrieveTranscript as e:
        return error(f"Не получилось достать субтитры: {type(e).__name__}", 502)

    snippets = [
        {"start": round(s.start, 2), "dur": round(s.duration, 2), "text": s.text.replace("\n", " ").strip()}
        for s in fetched
        if s.text.strip()
    ]
    return jsonify({
        "videoId": vid,
        "language": fetched.language,
        "languageCode": fetched.language_code,
        "auto": fetched.is_generated,
        "snippets": snippets,
    })


if __name__ == "__main__":
    port = 8765
    Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(host="127.0.0.1", port=port, debug=False)
