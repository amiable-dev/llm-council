"""LLM Council MCP Server - consult multiple LLMs and get synthesized guidance."""
from mcp.server.fastmcp import FastMCP
from llm_council.council import run_full_council



mcp = FastMCP("LLM Council")

@mcp.tool()
async def consult_council(query: str, include_details: bool = False) -> str:
    """
    Consult the LLM Council for guidance on a query.
    
    Args:
        query: The question to ask the council.
        include_details: If True, includes individual model responses and rankings.
    """
    # Run the council
    stage1, stage2, stage3, metadata = await run_full_council(query)
    
    chairman_response = stage3.get("response", "No response from Chairman.")
    
    result = f"### Chairman's Synthesis\n\n{chairman_response}\n"
    
    if include_details:
        result += "\n\n### Council Details\n"
        # Add Stage 1 details (Individual Responses)
        result += "\n#### Stage 1: Individual Opinions\n"
        for item in stage1:
            result += f"\n**{item['model']}**:\n{item['response']}\n"
            
        # Add Stage 2 details (Rankings)
        result += "\n#### Stage 2: Peer Review\n"
        for item in stage2:
            result += f"\n**{item['model']}** ranking:\n{item['ranking']}\n"
            
    return result

def main():
    """Entry point for the llm-council command."""
    mcp.run()


if __name__ == "__main__":
    main()
