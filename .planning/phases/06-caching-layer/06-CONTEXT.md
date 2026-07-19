# Phase 6: Caching Layer - Context

Cache only useful content. Keys include model, prompt version, and content hash;
page reuse expires after 90 days and blocked/JS-shell content is never stored.
