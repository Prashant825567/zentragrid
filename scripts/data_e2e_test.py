"""Real-Telegram end-to-end test for the document store.

Unlike the unit suite (which runs on the in-memory backend) this script talks
to the live channels defined in ``.env``. Its most important assertion is the
**cold rebuild**: after wiping the in-process index, every document must come
back byte-identical from Telegram alone.

Run:  python scripts/data_e2e_test.py
It cleans up everything it creates.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from app.core.storage import build_storage  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.services.document_service import DocumentService  # noqa: E402
from app.utils.ids import new_id  # noqa: E402

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  \033[32mPASS\033[0m  {label}")
    else:
        FAIL += 1
        print(f"  \033[31mFAIL\033[0m  {label} {detail}")


async def main() -> int:
    print("=" * 66)
    print("ZentraGrid document store - REAL TELEGRAM E2E")
    print("=" * 66)

    if settings.STORAGE_BACKEND != "telegram":
        print("STORAGE_BACKEND is not 'telegram' - aborting.")
        return 1

    storage = build_storage()
    service = DocumentService(storage)

    # A throwaway project id keeps this run isolated from any real data.
    project = Project(
        project_id=new_id("project", 12),
        owner_id=new_id("owner", 12),
        name="e2e-data",
    )
    collection = "e2e_notes"
    created_ids: list[str] = []

    print(f"\nproject   : {project.project_id}")
    print(f"collection: {collection}")
    print(f"data chan : {'dedicated' if settings.TG_DATA_CHANNEL else 'shared with METADATA'}")

    # ---------------------------------------------------------- 1. create
    print("\n[1] create + read")
    small = {"title": "Meeting notes", "tags": ["work", "q4"], "views": 12, "done": False}
    rec, body = await service.create(project, collection, small, doc_id="note-small")
    created_ids.append(rec.doc_id)
    check("small doc created", rec.rev == 1 and rec.doc_id == "note-small")
    check("small doc stored inline", rec.storage == "inline", f"(got {rec.storage})")
    check("body round-trips", body == small)

    got_rec, got_body = await service.get(project, collection, "note-small")
    check("read back equal", got_body == small)

    # ------------------------------------------------------- 2. big / blob
    print("\n[2] large document spills to a blob")
    big = {
        "title": "Long note",
        "kind": "big",
        "body": "L" * (settings.DOC_INLINE_MAX_BYTES + 20_000),
    }
    big_rec, _ = await service.create(project, collection, big, doc_id="note-big")
    created_ids.append(big_rec.doc_id)
    check("big doc marked blob", big_rec.storage == "blob", f"(got {big_rec.storage})")
    check("blob pointer set", big_rec.blob_message_id is not None)
    check("inline data cleared", big_rec.data is None)

    _, big_body = await service.get(project, collection, "note-big")
    check("blob body round-trips exactly", big_body == big)

    # ---------------------------------------------------------- 3. updates
    print("\n[3] replace, merge, revisions")
    rec2, body2 = await service.set(
        project, collection, "note-small", {"title": "Replaced", "views": 1}
    )
    check("rev bumped on replace", rec2.rev == 2, f"(got {rec2.rev})")
    check("replace drops old fields", "tags" not in body2)

    rec3, body3 = await service.merge(
        project, collection, "note-small", {"meta": {"pinned": True}}
    )
    check("rev bumped on merge", rec3.rev == 3, f"(got {rec3.rev})")
    check("merge keeps existing fields", body3["title"] == "Replaced")
    check("merge adds nested field", body3["meta"] == {"pinned": True})

    try:
        await service.set(
            project, collection, "note-small", {"x": 1}, expected_rev=1
        )
        check("stale expected_rev rejected", False, "(no error raised)")
    except Exception as exc:  # noqa: BLE001
        check("stale expected_rev rejected", type(exc).__name__ == "RevisionConflictError")

    # ----------------------------------------------------------- 4. query
    print("\n[4] queries")
    for index in range(3):
        rec_n, _ = await service.create(
            project,
            collection,
            {"title": f"bulk-{index}", "views": index * 10, "kind": "bulk"},
            doc_id=f"bulk-{index}",
        )
        created_ids.append(rec_n.doc_id)

    rows, _ = await service.query(
        project, collection, filters=[("kind", "eq", "bulk")]
    )
    check("filter eq", len(rows) == 3, f"(got {len(rows)})")

    rows, _ = await service.query(
        project, collection, filters=[("views", "gte", 10), ("kind", "eq", "bulk")]
    )
    check("two filters ANDed", len(rows) == 2, f"(got {len(rows)})")

    rows, _ = await service.query(
        project, collection, filters=[("kind", "eq", "bulk")], order_by="views", desc=True
    )
    check("order_by desc", [r[1]["views"] for r in rows] == [20, 10, 0])

    page1, cursor = await service.query(
        project, collection, filters=[("kind", "eq", "bulk")], order_by="views", limit=2
    )
    check("page 1 size", len(page1) == 2)
    check("cursor issued", cursor is not None)
    page2, cursor2 = await service.query(
        project,
        collection,
        filters=[("kind", "eq", "bulk")],
        order_by="views",
        limit=2,
        cursor=cursor,
    )
    check("page 2 size", len(page2) == 1, f"(got {len(page2)})")
    check("no overlap between pages", not ({r[0].doc_id for r in page1} & {r[0].doc_id for r in page2}))
    check("pagination terminates", cursor2 is None)

    rows, _ = await service.query(project, collection, filters=[("kind", "eq", "big")])
    check("blob document is queryable", len(rows) == 1 and rows[0][0].doc_id == "note-big")

    cols = await service.collections(project)
    check("collection listed", (collection, 5) in cols, f"(got {cols})")

    # ----------------------------------------------- 5. COLD INDEX REBUILD
    print("\n[5] cold rebuild - wipe the index, reload from Telegram only")
    storage.documents.reset_index()
    check("index is empty after reset", len(storage.documents._by_pk) == 0)

    rebuilt = build_storage()
    rebuilt_service = DocumentService(rebuilt)
    await rebuilt.documents.ensure_loaded()

    r_rec, r_body = await rebuilt_service.get(project, collection, "note-small")
    check("small doc survived restart", r_body == body3, "(content drifted)")
    check("revision survived restart", r_rec.rev == 3, f"(got {r_rec.rev})")

    _, r_big = await rebuilt_service.get(project, collection, "note-big")
    check("blob doc survived restart", r_big == big)

    r_rows, _ = await rebuilt_service.query(
        project, collection, filters=[("kind", "eq", "bulk")]
    )
    check("queries work after restart", len(r_rows) == 3, f"(got {len(r_rows)})")

    r_cols = await rebuilt_service.collections(project)
    check("collections rebuilt", (collection, 5) in r_cols, f"(got {r_cols})")

    # -------------------------------------------------------- 6. isolation
    print("\n[6] project isolation")
    other = Project(project_id=new_id("project", 12), owner_id="owner_other", name="other")
    other_rows, _ = await rebuilt_service.query(other, collection)
    check("other project sees nothing", other_rows == [])
    other_cols = await rebuilt_service.collections(other)
    check("other project has no collections", other_cols == [])

    # ---------------------------------------------------------- 7. cleanup
    print("\n[7] cleanup")
    for doc_id in created_ids:
        try:
            await rebuilt_service.delete(project, collection, doc_id)
        except Exception as exc:  # noqa: BLE001
            print(f"      cleanup warning {doc_id}: {type(exc).__name__}")

    remaining, _ = await rebuilt_service.query(project, collection)
    check("all documents deleted", remaining == [], f"(left {len(remaining)})")
    check("collection gone", await rebuilt_service.collections(project) == [])

    final = build_storage()
    await final.documents.ensure_loaded()
    leftovers = [
        r for r in final.documents._by_pk.values() if r.project_id == project.project_id
    ]
    check("channel clean after restart", leftovers == [], f"(left {len(leftovers)})")

    # -------------------------------------------------------------- report
    print("\n" + "=" * 66)
    total = PASS + FAIL
    print(f"RESULT: {PASS}/{total} checks passed")
    print("=" * 66)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
