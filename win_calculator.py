import json


# Embedded payout table
payOutTable = {
    "Three In A Row": {
        "reel_icon_9.png": 2,
        "reel_icon_8.png": 3,
        "reel_icon_7.png": 4,
        "reel_icon_6.png": 5,
        "reel_icon_5.png": 10,
        "reel_icon_4.png": 15,
        "reel_icon_3.png": 15,
        "reel_icon_2.png": 40,
        "reel_icon_1.png": 100
    },
    "Four In A Row": {
        "reel_icon_9.png": 15,
        "reel_icon_8.png": 20,
        "reel_icon_7.png": 20,
        "reel_icon_6.png": 40,
        "reel_icon_5.png": 40,
        "reel_icon_4.png": 80,
        "reel_icon_3.png": 80,
        "reel_icon_2.png": 200,
        "reel_icon_1.png": 500
    },
    "Five In A Row": {
        "reel_icon_9.png": 25,
        "reel_icon_8.png": 30,
        "reel_icon_7.png": 30,
        "reel_icon_6.png": 75,
        "reel_icon_5.png": 75,
        "reel_icon_4.png": 150,
        "reel_icon_3.png": 150,
        "reel_icon_2.png": 300,
        "reel_icon_1.png": 1000
    },
    "In Any Reel": {
        "reel_icon_9.png": 1
    }
}

# Function to calculate win
def calculate_win(results, bet_amount, credits):
    global payOutTable

    print("Calculating win for:", results, "Bet amount:", bet_amount, "Credits:", credits)

    # Check if credits are sufficient for the bet
    if credits + bet_amount < bet_amount:
        print("Insufficient credits for the bet.")
        return 0, credits  # Return 0 win and current credits

    # Initialize win to 0 for each calculation
    win = 0

    try:
        # Check for consecutive icons
        if results[0] == results[1] == results[2]:  # Three in a row
            win = payOutTable['Three In A Row'].get(results[0], 0) * bet_amount
            if len(results) > 3 and results[3] == results[0]:  # Four in a row
                win = payOutTable['Four In A Row'].get(results[0], 0) * bet_amount
                if len(results) > 4 and results[4] == results[0]:  # Five in a row
                    win = payOutTable['Five In A Row'].get(results[0], 0) * bet_amount

        # Check for special icon in any reel
        special_icon = next(iter(payOutTable['In Any Reel']))  # Get the special icon
        special_icon_payout = payOutTable['In Any Reel'][special_icon]
        
        if bet_amount == 3:
            if special_icon in results[:3]:
                win += special_icon_payout * bet_amount
        elif bet_amount == 6:
            if special_icon in results[:3] and special_icon in results[3:4]:
                win += 2 * special_icon_payout * bet_amount
            elif special_icon in results[:4]:
                win += special_icon_payout * bet_amount
        elif bet_amount == 9:
            if special_icon in results[:3] and special_icon in results[3:4] and special_icon in results[4:5]:
                win += 4 * special_icon_payout * bet_amount
            elif (special_icon in results[:3] and special_icon in results[3:5]) or (special_icon in results[3:5] and special_icon in results[:3]):
                win += 2 * special_icon_payout * bet_amount
            elif special_icon in results[:5]:
                win += special_icon_payout * bet_amount

        # Update credits total
        credits += win
        print("Win:", win, "Updated Credits:", credits)
        return win, credits
    except Exception as e:
        print("Error during win calculation:", e)
        return 0, credits  # Return default values in case of error


