# V0 - Initial implementation
# main.py

import typer

app = typer.Typer(name="nl2sql-engine", help="Natural language to SQL engine.")


@app.command()
def query(
    nl_query: str = typer.Argument(..., help="Natural language query to convert to SQL."),
    app_id: str = typer.Option(None, "--app-id", help="Target app schema ID."),
    output: str = typer.Option("human", "--output", help="Output format: human | json | sql."),
):
    """Convert a natural language query to SQL."""
    typer.echo(f"Query received: {nl_query}")
    typer.echo("Pipeline not yet implemented — Story 1.1 scaffold only.")


if __name__ == "__main__":
    app()
