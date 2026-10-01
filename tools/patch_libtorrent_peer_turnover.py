from __future__ import annotations

import argparse
from pathlib import Path

from patch_libtorrent_no_piece_upload import function_span


MARKER = "DOWNLOAD_ONLY_TORRENT_TURNOVER_GRACE"
GRACE_SECONDS = 120

COMPARE_SIGNATURE = (
    "bool compare_disconnect_peer(peer_connection const* lhs, peer_connection const* rhs)"
)
DISCONNECT_SIGNATURE = "int torrent::disconnect_peers(int const num, error_code const& ec)"

# Upstream shape this patch was written against (libtorrent 2.1.1).
EXPECTED = {
    COMPARE_SIGNATURE: (
        "lhs->is_seed() != rhs->is_seed()",
        "total_payload_download()",
        "lhs->is_choked() != rhs->is_choked()",
    ),
    DISCONNECT_SIGNATURE: (
        "std::partial_sort_copy(m_connections.begin(), m_connections.end()",
        "p->disconnect(ec, operation_t::bittorrent);",
    ),
}

COMPARE_BODY = r'''{
		// Download Only Torrent: rank peers by what they deliver now.
		//
		// Upstream drops every non-seed before any seed and ranks the rest by
		// their average rate over the whole connection, so a fast non-seed, or a
		// peer that only just started sending, was dropped before a seed that
		// sends nothing. (Its "chokes us" test also read our own choke flag.)

		// prefer to disconnect peers that are already disconnecting
		if (lhs->is_disconnecting() != rhs->is_disconnecting())
			return lhs->is_disconnecting();

		// prefer to disconnect peers we're not interested in
		if (lhs->is_interesting() != rhs->is_interesting())
			return rhs->is_interesting();

		// prefer to disconnect peers that send us less right now
		int const lhs_rate = lhs->statistics().download_payload_rate();
		int const rhs_rate = rhs->statistics().download_payload_rate();
		if (lhs_rate != rhs_rate)
			return lhs_rate < rhs_rate;

		// prefer to disconnect peers that choke us
		if (lhs->has_peer_choked() != rhs->has_peer_choked())
			return lhs->has_peer_choked();

		// prefer to disconnect peers that are on parole
		if (lhs->on_parole() != rhs->on_parole())
			return lhs->on_parole();

		// prefer to disconnect non-seeds; a seed may still unchoke us
		if (lhs->is_seed() != rhs->is_seed())
			return rhs->is_seed();

		// prefer to disconnect peers that sent less over the whole connection
		std::int64_t lhs_transferred = lhs->statistics().total_payload_download();
		std::int64_t rhs_transferred = rhs->statistics().total_payload_download();

		time_point const now = aux::time_now();
		std::int64_t const lhs_time_connected = total_seconds(now - lhs->connected_time());
		std::int64_t const rhs_time_connected = total_seconds(now - rhs->connected_time());

		lhs_transferred /= lhs_time_connected + 1;
		rhs_transferred /= (rhs_time_connected + 1);
		if (lhs_transferred != rhs_transferred)
			return lhs_transferred < rhs_transferred;

		return lhs->last_received() < rhs->last_received();
	}'''

DISCONNECT_BODY = r'''{
		INVARIANT_CHECK;

#if TORRENT_USE_ASSERTS
		// make sure we don't have any dangling pointers
		for (auto p : m_connections)
		{
			TORRENT_INCREMENT(m_iterating_connections);
			TORRENT_ASSERT(m_ses.has_peer(p));
		}
#endif
		// Download Only Torrent: peer turnover (optimistic disconnect) leaves
		// alone the peers we want pieces from that are either new, so they get
		// time to ramp up, or sending to us right now. Other callers (limits,
		// shutdown) are unaffected.
		bool const turnover = ec == error_code(errors::optimistic_disconnect);
		time_point const now = aux::time_now();
		std::vector<peer_connection*> candidates;
		candidates.reserve(m_connections.size());
		int kept = 0;
		for (auto* p : m_connections)
		{
			if (turnover
				&& !p->is_disconnecting()
				&& p->is_interesting()
				&& (now - p->connected_time() < seconds(@GRACE@)
					|| p->statistics().download_payload_rate() > 0))
			{
				++kept;
				continue;
			}
			candidates.push_back(p);
		}

#ifndef TORRENT_DISABLE_LOGGING
		if (turnover && should_log())
		{
			debug_log("DOWNLOAD_ONLY_TORRENT_TURNOVER_GRACE kept %d of %d peers"
				, kept, static_cast<int>(m_connections.size()));
		}
#else
		(void)kept;
#endif

		std::vector<peer_connection*> to_disconnect;
		to_disconnect.resize(static_cast<std::size_t>(
			std::max(0, std::min(num, static_cast<int>(candidates.size())))));
		auto end = std::partial_sort_copy(candidates.begin(), candidates.end()
			, to_disconnect.begin(), to_disconnect.end(), compare_disconnect_peer);
		for (auto it = to_disconnect.begin(); it != end; ++it)
		{
			peer_connection* p = *it;
			TORRENT_ASSERT(p->associated_torrent().lock().get() == this);
			p->disconnect(ec, operation_t::bittorrent);
		}
		return static_cast<int>(end - to_disconnect.begin());
	}'''.replace("@GRACE@", str(GRACE_SECONDS))


def _replace_body(text: str, signature: str, body: str) -> str:
    start, end = function_span(text, signature)
    current = text[start:end]
    if MARKER in current or "Download Only Torrent" in current:
        return text
    for token in EXPECTED[signature]:
        if token not in current:
            raise RuntimeError(
                f"upstream shape changed in {signature!r}: expected {token!r}"
            )
    return text[:start] + body + text[end:]


def patch(path: Path) -> None:
    original = path.read_text(encoding="utf-8")
    patched = _replace_body(original, COMPARE_SIGNATURE, COMPARE_BODY)
    patched = _replace_body(patched, DISCONNECT_SIGNATURE, DISCONNECT_BODY)
    if patched == original:
        print(f"Already patched: {path}")
    else:
        path.write_text(patched, encoding="utf-8", newline="\n")
        print(f"Patched: {path}")

    compare = patched[slice(*function_span(patched, COMPARE_SIGNATURE))]
    disconnect = patched[slice(*function_span(patched, DISCONNECT_SIGNATURE))]
    if "has_peer_choked()" not in compare or "download_payload_rate()" not in compare:
        raise RuntimeError("compare_disconnect_peer was not replaced")
    if MARKER not in disconnect or f"seconds({GRACE_SECONDS})" not in disconnect:
        raise RuntimeError("turnover grace period missing after patch")
    print("Verified peer turnover grace period and ranking.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    patch(args.source.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
