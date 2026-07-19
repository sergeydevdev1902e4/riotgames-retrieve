import gzip
import json
import sqlite3
from pathlib import Path
import pytest
from riotgames_retrieve.storage import StorageEngine


@pytest.fixture
def temp_storage(tmp_path):
    db_path = tmp_path / "test_archive.db"
    data_dir = tmp_path / "raw_data"
    data_dir.mkdir()
    return StorageEngine(db_path=str(db_path), output_dir=str(data_dir))


def test_db_init_and_tables_exist(temp_storage):
    with sqlite3.connect(temp_storage.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        assert "matches" in tables
        assert "crawl_seeds" in tables
        assert "schema_version" in tables


def test_upsert_match_metadata(temp_storage):
    metadata = {
        "match_id": "EUW1_12345678",
        "region": "euw1",
        "queue_id": 420,
        "game_creation": 1700000000000,
        "game_duration": 1820,
        "has_timeline": 0,
    }
    temp_storage.save_match_meta(metadata)
    
    metadata["has_timeline"] = 1
    temp_storage.save_match_meta(metadata)
    
    with sqlite3.connect(temp_storage.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT has_timeline FROM matches WHERE match_id = ?", ("EUW1_12345678",))
        row = cursor.fetchone()
        assert row[0] == 1


def test_is_match_archived(temp_storage):
    assert not temp_storage.is_match_archived("NA1_999999")
    temp_storage.save_match_meta({
        "match_id": "NA1_999999",
        "region": "na1",
        "queue_id": 420,
        "game_creation": 1700000000000,
        "game_duration": 1200,
        "has_timeline": 1,
    })
    assert temp_storage.is_match_archived("NA1_999999")


def test_compressed_timeline_writer(temp_storage):
    timeline_payload = {
        "metadata": {"matchId": "KR_55511122"},
        "info": {"frameInterval": 60000, "frames": [{"events": [], "participantFrames": {}}]}
    }
    
    gz_path = temp_storage.write_timeline_gz("KR_55511122", timeline_payload)
    assert Path(gz_path).exists()
    assert str(gz_path).endswith(".json.gz")
    
    with gzip.open(gz_path, "rt", encoding="utf-8") as f:
        data = json.load(f)
        assert data["metadata"]["matchId"] == "KR_55511122"
        assert data["info"]["frameInterval"] == 60000


def test_seed_puuid_lifecycle(temp_storage):
    puuid = "test-puuid-12345"
    temp_storage.add_seed(puuid, region="kr")
    
    # adding again should not crash (INSERT OR IGNORE)
    temp_storage.add_seed(puuid, region="kr")
    
    unprocessed = temp_storage.get_pending_seeds(limit=10)
    assert puuid in unprocessed
    
    temp_storage.mark_seed_done(puuid)
    unprocessed_after = temp_storage.get_pending_seeds(limit=10)
    assert puuid not in unprocessed_after
