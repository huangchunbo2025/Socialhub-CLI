"""AI insights generator — summarizes plan results."""

from .client import call_ai_api


def generate_insights(query: str, results: list[dict]) -> str:
    """Generate AI insights based on query results."""
    results_text = ""
    for r in results:
        if r["success"] and r["output"]:
            results_text += f"\n### {r['description']}\n```\n{r['output'][:2000]}\n```\n"

    if not results_text:
        return ""

    insight_prompt = f"""User query: {query}

The following are the data results from the analysis:
{results_text}

Please provide concise insight analysis based on the above data:
1. Key findings (2-3 points)
2. Trend analysis
3. Business recommendations (1-2 actionable suggestions)

Output insights directly, no commands. Be concise and professional."""

    return call_ai_api(insight_prompt, show_thinking=False)
