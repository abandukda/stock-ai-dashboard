from datetime import datetime
from alerts import send_alerts

def main():
    print("=" * 50)
    print(f"Running AI stock alerts at {datetime.now()}")

    result = send_alerts()

    print(result)
    print("=" * 50)


if __name__ == "__main__":
    main()