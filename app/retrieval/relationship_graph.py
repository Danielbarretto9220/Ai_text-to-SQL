"""
get_join_path(table_a, table_b): BFS over meta.relationships to give the
LLM a pre-computed join path instead of asking it to infer one. Also used
for relationship-expansion (pull in directly-joined tables post-retrieval).

Not yet implemented — see enterprise-text-to-sql-architecture.md §1.4, §2.1.
"""
