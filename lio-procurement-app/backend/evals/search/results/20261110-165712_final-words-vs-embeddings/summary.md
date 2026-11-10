# Search eval 20261110-165712 (final-words-vs-embeddings)

| method | right | wrong sure | missed | correct nothing | top-5 hit | median ms |
|---|---|---|---|---|---|---|
| words | 39/40 | 0 | 1 | 19/19 | 40/40 | 5.6 |
| embeddings | 11/40 | 0 | 29 | 19/19 | 40/40 | 282.1 |

Settings: `{"methods": ["words", "embeddings"], "threshold": null, "margin": null, "defaults": {"words": {"threshold": 0.65, "margin": 0.15}, "embeddings": {"threshold": 0.4, "margin": 0.17}}, "embedding_model": "text-embedding-3-small", "cases": 59, "answer_key": "drafted, not yet checked by Adrian"}`
