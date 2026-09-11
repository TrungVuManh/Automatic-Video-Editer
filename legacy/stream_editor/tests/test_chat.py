import json

from pipeline.s2_preprocess import parse_chat


def test_youtube_chat(tmp_path):
    def line(ms, user, runs):
        return json.dumps({"replayChatItemAction": {"videoOffsetTimeMsec": str(ms), "actions": [
            {"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {
                "message": {"runs": runs}, "authorName": {"simpleText": user}}}}}]}})
    p = tmp_path / "c.json"
    p.write_text("\n".join([
        line(5000, "An", [{"text": "gg "}, {"emoji": {"shortcuts": [":fire:"]}}]),
        line(2000, "Nightbot", [{"text": "follow đi"}]),
        line(1000, "Bình", [{"text": "kkk"}]),
    ]), encoding="utf-8")
    msgs = parse_chat(p, "youtube")
    assert [m["text"] for m in msgs] == ["kkk", "gg :fire:"]
    assert msgs[1]["t"] == 5.0


def test_twitch_chat(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"comments": [
        {"content_offset_seconds": 12.5, "commenter": {"display_name": "Cuong"}, "message": {"body": "LUL"}},
        {"content_offset_seconds": 3.0, "commenter": {"display_name": "StreamElements"}, "message": {"body": "!"}},
    ]}), encoding="utf-8")
    msgs = parse_chat(p, "twitch")
    assert msgs == [{"t": 12.5, "user": "Cuong", "text": "LUL"}]
