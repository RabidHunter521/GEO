"""Anonymous read of a published index edition (Phase 6 Task 7).

The only route in SeenBy reachable with no credential and no share token, so
its surface is deliberately tiny: fetch one published edition by slug, or 404.

Three properties matter more than the code:

* **It reads a table anonymous roles cannot touch.** `benchmark_publications`
  has RLS enabled and `anon` revoked; the payload reaches the public only
  through this server route, which decides what is servable.
* **Withdrawal takes effect immediately.** The query filters on
  `status = 'published'`, so a withdrawn edition 404s on the next request
  without anything being deleted.
* **It is rate-limited and non-indexable.** A public aggregate endpoint is
  where a scraper would go to diff editions over time.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.schemas.benchmark_publication import PublicationPublic
from app.services import benchmark_publication_service as service

# Its own namespace and budget: this route is anonymous, so it must not share
# a bucket with the share-link surface where a real client's page load lives.
_public_rate_limit = rate_limit("public_benchmarks", max_requests=60, window_seconds=60)

router = APIRouter(
    prefix="/public/benchmarks",
    tags=["public-benchmarks"],
    dependencies=[Depends(_public_rate_limit)],
)


@router.get("/{slug}", response_model=PublicationPublic)
def get_published_edition(slug: str, response: Response, db: Session = Depends(get_db)):
    publication = service.get_published(db, slug)
    if publication is None:
        # Uniform 404 for unknown, draft, approved-but-unpublished, and
        # withdrawn alike — the response must not reveal that a slug exists in
        # a state the caller is not allowed to see.
        raise HTTPException(status_code=404, detail="Not found")

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return PublicationPublic.from_model(publication)
