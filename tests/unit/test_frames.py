import pytest
from maya_agent.core.frames import encode_frame, FrameDecoder, FrameError


def test_encode_frame_prefixes_with_4_byte_length():
    payload = {"hello": "world"}
    frame = encode_frame(payload)
    assert isinstance(frame, bytes)
    # 4-byte big-endian length + JSON body
    body = b'{"hello": "world"}'
    assert int.from_bytes(frame[:4], "big") == len(body)
    assert frame[4:] == body


def test_decoder_yields_one_message_per_frame():
    d = FrameDecoder()
    f1 = encode_frame({"a": 1})
    f2 = encode_frame({"b": 2})
    msgs = list(d.feed(f1 + f2))
    assert msgs == [{"a": 1}, {"b": 2}]


def test_decoder_handles_split_across_chunks():
    d = FrameDecoder()
    full = encode_frame({"x": "y"})
    msgs1 = list(d.feed(full[:3]))
    assert msgs1 == []
    msgs2 = list(d.feed(full[3:]))
    assert msgs2 == [{"x": "y"}]


def test_decoder_handles_split_inside_body():
    d = FrameDecoder()
    full = encode_frame({"x": "long-ish payload to ensure split"})
    cut = len(full) // 2
    msgs1 = list(d.feed(full[:cut]))
    assert msgs1 == []
    msgs2 = list(d.feed(full[cut:]))
    assert len(msgs2) == 1


def test_decoder_rejects_oversize_frame():
    d = FrameDecoder(max_frame_bytes=10)
    huge = encode_frame({"big": "x" * 1000})
    with pytest.raises(FrameError, match="frame too large"):
        list(d.feed(huge))


def test_decoder_rejects_invalid_json():
    d = FrameDecoder()
    bad = (5).to_bytes(4, "big") + b"not{j"
    with pytest.raises(FrameError, match="invalid JSON"):
        list(d.feed(bad))
