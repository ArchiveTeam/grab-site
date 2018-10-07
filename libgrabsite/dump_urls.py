import click
import sqlite3
import libgrabsite

def print_version(ctx, param, value):
	if not value or ctx.resilient_parsing:
		return
	click.echo(libgrabsite.__version__)
	ctx.exit()


@click.command()

@click.option("--version", is_flag=True, callback=print_version,
	expose_value=False, is_eager=True, help="Print version and exit.")

@click.argument("wpull_db_file", type=str)

@click.argument("status", type=click.Choice(["done", "error", "in_progress", "skipped", "todo"]))

def main(wpull_db_file, status):
	"""
	Dumps URLs of a particular crawl status from a wpull.db file.

	WPULL_DB_FILE is the path to the wpull.db file.

	STATUS is one of "done", "error", "in_progress", "skipped", or "todo".
	"""
	conn = sqlite3.connect(wpull_db_file)
	c = conn.cursor()

	rows = c.execute(
		"SELECT url_strings.url FROM queued_urls "
		"JOIN url_strings ON queued_urls.url_string_id=url_strings.id "
		"WHERE status=?;", (status,))
	for row in rows:
		print(row[0])


if __name__ == "__main__":
	main()
