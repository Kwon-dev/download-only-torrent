from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import patch_libtorrent_peer_turnover as turnover  # noqa: E402

# The two functions as they appear in upstream libtorrent v2.1.1 src/torrent.cpp.
UPSTREAM = r'''
namespace {
	bool compare_disconnect_peer(peer_connection const* lhs, peer_connection const* rhs)
	{
		if (lhs->is_disconnecting() != rhs->is_disconnecting())
			return lhs->is_disconnecting();
		if (lhs->is_interesting() != rhs->is_interesting())
			return rhs->is_interesting();
		if (lhs->is_seed() != rhs->is_seed())
			return rhs->is_seed();
		std::int64_t lhs_transferred = lhs->statistics().total_payload_download();
		std::int64_t rhs_transferred = rhs->statistics().total_payload_download();
		if (lhs->is_choked() != rhs->is_choked())
			return lhs->is_choked();
		return lhs->last_received() < rhs->last_received();
	}
}

	int torrent::disconnect_peers(int const num, error_code const& ec)
	{
		aux::vector<peer_connection*> to_disconnect;
		to_disconnect.resize(num);
		auto end = std::partial_sort_copy(m_connections.begin(), m_connections.end()
			, to_disconnect.begin(), to_disconnect.end(), compare_disconnect_peer);
		for (auto* p : aux::range(to_disconnect.begin(), end))
		{
			p->disconnect(ec, operation_t::bittorrent);
		}
		return static_cast<int>(end - to_disconnect.begin());
	}

	void torrent::finished() { /* "{" in a string and } in a comment */ }
'''


def test_turnover_patch_applies_once_and_keeps_other_code(tmp_path):
    source = tmp_path / "torrent.cpp"
    source.write_text(UPSTREAM, encoding="utf-8")

    turnover.patch(source)
    patched = source.read_text(encoding="utf-8")
    assert turnover.MARKER in patched
    assert "seconds(120)" in patched
    assert "has_peer_choked()" in patched
    assert "lhs->is_choked()" not in patched
    assert "void torrent::finished()" in patched

    turnover.patch(source)  # idempotent
    assert source.read_text(encoding="utf-8") == patched


def test_turnover_patch_refuses_an_unknown_upstream_shape(tmp_path):
    source = tmp_path / "torrent.cpp"
    source.write_text(UPSTREAM.replace("lhs->is_seed() != rhs->is_seed()", ""), encoding="utf-8")
    with pytest.raises(RuntimeError, match="upstream shape changed"):
        turnover.patch(source)
