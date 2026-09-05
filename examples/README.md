# Orcaset Examples

These self-contained examples demonstrate common financial-modeling patterns and orcaset features.

## Examples

| Example | Feature |
| --- | --- |
| [Capex cohorts](capex-cohorts/) | Maps each capex period to a nested depreciation schedule, then rolls the cohorts into total depreciation. |
| [Citations](citations/) | Attaches filing metadata to sourced values via a float subclass so provenance travels with the leaf while derived cells stay ordinary numbers. |
| [Extend series](extend-series/) | Composes a finite historical series with a later forecast so one line answers both sides of the seam. |
| [Iterative solver](iterative-solver/) | Solves a cyclic value dependency for capitalized interest on average debt. |
| [Series composition](series-composition/) | Combine linked-list series with typed arithmetic combinators. |
| [Paper LBO](paper-lbo/) | Models a basic leveraged buyout with pro forma financials and IRR sensitivity. |
| [Typed units](typed-units/) | Prevents accidental cross-currency combinations using custom value types. |
| [Web scraping](web-scraping/) | Embeds inline data retrieval over the web and JSON parsing to directly ingest data from an outside data source. |

Open an example's README for its model structure, highlighted feature, and run instructions.
