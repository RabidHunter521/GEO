# SeenBy Measurement Methodology

## Measurement layers

SeenBy reports four related but distinct measurement layers. Keeping them separate prevents an observation about AI answers, a readiness indicator, and a commercial outcome from being presented as the same kind of evidence.

### AI Presence

AI Presence records whether a business is Seen by AI in observed answers to the tracked buyer-query set. It covers observed recommendations, platform coverage, and competitor share of voice across that set. It is evidence from the completed scan, not a claim about every question that a potential customer may ask.

### Accuracy and Reputation

Accuracy and Reputation records potential conflicts between observed model answers and approved business facts. A finding remains needs-review until a human confirms it. This layer routes factual risks for review; it does not make a professional, legal, medical, or regulatory determination.

### Growth Readiness

Growth Readiness is the current composite leading indicator. In version v1.4.0, it combines AI citability (40%), brand authority (20%), content quality (20%), verified robots.txt AI-crawler access (10%), and verified structured data (10%). Brand authority and content quality are assisted suggestions that an administrator reviews against public evidence before they affect the score. Growth Readiness is returned as `overall_score` in the current API; it is not a measure of confirmed traffic, leads, or revenue.

### Business Impact

Business Impact keeps observed traffic and intent events separate from attributed, assisted, and estimated leads or revenue. It is designed to show what is recorded, what has a defined source relationship, what involved SeenBy work, and what is calculated from assumptions without turning a modelled outcome into confirmed revenue.

## Query coverage

SeenBy monitors the enabled client platforms: ChatGPT, Perplexity, Gemini, and Claude. Each client has a configured set of brand, comparison, recommendation, and local query templates. The scan engine can run up to 20 queries per enabled platform: up to five in each category, with comparison queries capped by the number of configured competitors. It can also track competitor queries and up to five control queries that are deliberately left unchanged for comparison. Client industry, brand, competitor, location, and city values fill the applicable templates.

The configured query universe is a monitored sample, not every real question a buyer might ask. It is selected to make repeatable comparison possible and must be interpreted together with its enabled platforms, locations, and query configuration.

## Sampling and variability

Generated answers can vary between runs, platforms, model versions, locations, and sessions. A single observed change is evidence, not proof of a durable market shift. A scan reports what appeared in its configured sample at that time; it cannot reproduce an individual consumer's exact experience or establish that one change caused another without supporting comparison evidence.

## Technical and publisher files

robots.txt controls crawler access, and SeenBy's Technical Foundations dimension currently reflects verified robots.txt AI-crawler access. Structured data describes page entities, and verified structured data drives the separate Structured Data dimension. llms.txt and llms-full.txt are optional publisher-supplied formats that SeenBy can generate and verify for publishing purposes. Their presence does not independently increase Growth Readiness and does not guarantee AI visibility.

## Attribution and estimates

Observed means an event recorded in a source such as a traffic snapshot or configured analytics data. Attributed means an event classified to a defined source or referral path, rather than a claim that visibility caused the event. Assisted means SeenBy work was part of the documented path to an outcome but is not asserted to be the sole cause. Estimated means a transparent calculation, not a recorded commercial result.

Where a client has an average deal value, SeenBy estimates pipeline from AI-referral visitors using the configured visitor-to-lead percentage, average deal value, and lead-to-customer close-rate percentage. If the client has not configured a deal value, SeenBy does not produce that estimate. The current defaults are 2% visitor-to-lead and 20% lead-to-customer; administrators can override them per client. Estimated pipeline and estimated won value are not confirmed revenue.

## Versioning

The current score contract is v1.4.0. Historical score rows retain the score version under which they were computed and are not recomputed when the contract changes. This preserves the record of what each historical score meant at the time it was produced.

## Limitations

Platform coverage is limited to the enabled supported platforms and their available APIs; API responses can differ from consumer-facing experiences. The monitored sample is subject to the variability described above, and referral identification can be incomplete when a source does not expose a recognizable referrer. Accuracy findings are routed for factual review against approved evidence, while professional compliance advice remains the responsibility of qualified reviewers.
