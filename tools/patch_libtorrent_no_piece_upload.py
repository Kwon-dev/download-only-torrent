from __future__ import annotations

import argparse
from pathlib import Path


SIGNATURE = "void bt_peer_connection::write_piece(peer_request const& r, disk_buffer_holder buffer)"
MARKER = "DOWNLOAD_ONLY_TORRENT_PIECE_UPLOAD_DISABLED"
FORBIDDEN = (
    "append_send_buffer",
    "append_const_send_buffer",
    "m_payloads.emplace_back",
    "msg_piece",
)

REPLACEMENT_BODY = r'''{
		// Download Only Torrent hardening patch.
		//
		// The upstream implementation constructs a BitTorrent PIECE message and
		// appends the requested disk buffer to the socket send queue. This build
		// intentionally removes that code path entirely. Even if higher-level
		// choking/unchoke policy regresses, file piece payload cannot be queued
		// by this transport implementation.
		(void)buffer;

#ifndef TORRENT_DISABLE_LOGGING
		peer_log(peer_log_alert::outgoing_message, peer_log_alert::piece,
			"DOWNLOAD_ONLY_TORRENT_PIECE_UPLOAD_DISABLED p:%d s:%d l:%d",
			static_cast<int>(r.piece), r.start, r.length);
#endif

		// Treat any attempt to enter the removed upload path as a policy
		// violation and close this peer connection immediately.
		disconnect(errors::torrent_paused, operation_t::bittorrent);
	}'''


def function_span(text: str) -> tuple[int, int]:
    sig = text.find(SIGNATURE)
    if sig < 0:
        raise RuntimeError(f"function signature not found: {SIGNATURE}")

    brace = text.find("{", sig + len(SIGNATURE))
    if brace < 0:
        raise RuntimeError("opening brace not found for write_piece")

    depth = 0
    in_string = False
    in_char = False
    escape = False
    i = brace
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if escape:
            escape = False
            i += 1
            continue
        if (in_string or in_char) and ch == "\\":
            escape = True
            i += 1
            continue
        if not in_char and ch == '"':
            in_string = not in_string
            i += 1
            continue
        if not in_string and ch == "'":
            in_char = not in_char
            i += 1
            continue
        if in_string or in_char:
            i += 1
            continue

        if ch == "/" and nxt == "/":
            nl = text.find("\n", i + 2)
            if nl < 0:
                raise RuntimeError("unterminated line comment while parsing write_piece")
            i = nl + 1
            continue
        if ch == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            if end < 0:
                raise RuntimeError("unterminated block comment while parsing write_piece")
            i = end + 2
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return brace, i + 1
        i += 1

    raise RuntimeError("closing brace not found for write_piece")


def patch(path: Path) -> None:
    original = path.read_text(encoding="utf-8")
    start, end = function_span(original)
    current_body = original[start:end]

    if MARKER in current_body:
        print(f"Already patched: {path}")
        patched = original
    else:
        for token in FORBIDDEN:
            if token not in current_body:
                raise RuntimeError(
                    f"upstream write_piece shape changed: expected token {token!r} is missing"
                )
        patched = original[:start] + REPLACEMENT_BODY + original[end:]
        path.write_text(patched, encoding="utf-8", newline="\n")
        print(f"Patched: {path}")

    start, end = function_span(patched)
    body = patched[start:end]
    if MARKER not in body:
        raise RuntimeError("hard-disable marker missing after patch")
    leftovers = [token for token in FORBIDDEN if token in body]
    if leftovers:
        raise RuntimeError(f"forbidden upload primitives remain after patch: {leftovers}")

    print("Verified write_piece payload queueing primitives are absent.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    patch(args.source.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
