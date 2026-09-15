# 3rd tool description diff

## Before (2-tool loop: search_docs, get_openapi_spec)

```
search_docs: "Search the indexed developer documentation for text relevant
to a natural-language question. Use this first for anything that is not
about one specific endpoint's exact parameters or deprecation status."

get_openapi_spec: "Return the exact method, path, and parameter list for
one named GitHub endpoint at one specific API version. Use this only when
you already know the endpoint name and need its precise parameter shape --
not for open-ended search."
```

## After (3-tool loop: + check_deprecation)

```diff
 get_openapi_spec: "Return the exact method, path, and parameter list for
 one named GitHub endpoint at one specific API version. Use this only when
 you already know the endpoint name and need its precise parameter shape --
-not for open-ended search."
+not for open-ended search, and not to check whether something is
+deprecated (use check_deprecation for that)."

+check_deprecation: "Report whether a named endpoint has anything
+deprecated as of one specific API version, and what replaces it. Use this
+only to check deprecation status -- not to fetch the full parameter list
+(use get_openapi_spec instead) and not to search prose documentation
+(use search_docs instead)."
```

`check_deprecation` does one job (deprecation status + replacement), takes
an `api_version` enum instead of a free string, and its description names
the other two tools by name so the model can't confuse "what's the shape"
(get_openapi_spec) with "what's deprecated" (check_deprecation) with
"find relevant prose" (search_docs). Adding it required one clause added to
get_openapi_spec's description (steering away from the new tool) — no
rewrite of search_docs was needed since the overlap risk was only ever
between the two spec-lookup tools.
