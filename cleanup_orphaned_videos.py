"""Find and optionally delete orphaned R2 video objects.

Run on Render shell:
    python cleanup_orphaned_videos.py          # dry run - just list orphans
    python cleanup_orphaned_videos.py --delete  # actually delete them
"""

import os
import sys
import boto3
from database import get_db, BoutVideo, Lesson, TournamentPhoto

def main():
    delete = '--delete' in sys.argv

    # Connect to R2
    client = boto3.client('s3',
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY']
    )
    bucket = os.environ.get('R2_BUCKET_NAME', 'fencing-lessons')

    # List all R2 objects
    r2_keys = set()
    paginator = client.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get('Contents', []):
            r2_keys.add(obj['Key'])

    print(f"Total R2 objects: {len(r2_keys)}")

    # Get all known R2 keys from DB
    db = get_db()
    try:
        bout_video_keys = {v.r2_key for v in db.query(BoutVideo).all()}
        lesson_keys = {l.r2_object_key for l in db.query(Lesson).all() if l.r2_object_key}
        photo_keys = {p.r2_key for p in db.query(TournamentPhoto).all()}
    finally:
        db.close()

    db_keys = bout_video_keys | lesson_keys | photo_keys
    print(f"DB references: {len(bout_video_keys)} bout videos + {len(lesson_keys)} lessons + {len(photo_keys)} photos = {len(db_keys)} total")

    # Find orphans
    orphans = r2_keys - db_keys
    print(f"Orphaned R2 objects: {len(orphans)}")

    if not orphans:
        print("Nothing to clean up!")
        return

    for key in sorted(orphans):
        print(f"  {key}")

    if delete:
        print(f"\nDeleting {len(orphans)} orphaned objects...")
        for key in orphans:
            client.delete_object(Bucket=bucket, Key=key)
            print(f"  Deleted: {key}")
        print("Done.")
    else:
        print(f"\nDry run. Run with --delete to remove these {len(orphans)} objects.")

if __name__ == '__main__':
    main()
