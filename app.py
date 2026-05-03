from scanner import scan_market
from analyzer import analyze_stock

print("\n📊 STOCK AI SCANNER — TOP 15\n")

results = scan_market(limit=15)

for item in results:
    print(
        f"{item['ticker']:5} | "
        f"${item['price']:8.2f} | "
        f"Score: {item['score']:5} | "
        f"{item['signal']}"
    )

print("\n🔎 Manual stock analyzer")
ticker = input("Enter a ticker to analyze, or press Enter to skip: ")

if ticker.strip():
    result = analyze_stock(ticker)

    if result:
        print(f"\n{result['ticker']} Analysis")
        print(f"Price: ${result['price']}")
        print(f"Score: {result['score']}")
        print(f"Signal: {result['signal']}")
        print(f"Long-term outlook: {result['long_term']}")
        print("Reasons:")
        for reason in result["reasons"]:
            print(f"- {reason}")
    else:
        print("Could not analyze that ticker.")