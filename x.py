from tabulate import tabulate

from src.services.spa_service import fetch_data_from_api, get_data_actual


def main():
    url = "http://127.0.0.1:5500/src/assets/response.html"

    df = fetch_data_from_api(url, "", "")

    data_actual = get_data_actual(df)

    with open("x-output.txt", "w", encoding="utf-8") as f:
        f.write(tabulate(data_actual, headers="keys", tablefmt="psql"))


if __name__ == "__main__":
    main()
