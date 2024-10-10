# Standard library imports
import os
import sys
import random
import threading
from decimal import Decimal, ROUND_HALF_UP

# Third-party library imports
import pygame
import pygame.font
import pygame.mixer
import pygame_gui

# Local imports
from five_reel_value_gen import spin_reels
import win_calculator
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
from buyIn import process_transaction
from cashOut import send_doge

# Initialize Pygame and the mixer
pygame.init()
pygame.mixer.init()

# Screen settings
WINDOW_WIDTH = 1024
WINDOW_HEIGHT = 585
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("Slot Machine")

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

# Game settings
REEL_WIDTH = 100
REEL_HEIGHT = 500
REEL_OVERLAY_ALPHA = 220  # Transparency level (0-255)
spin_speed = 8  # Spin speed (pixels per frame)
frame_rate = 60  # Frame rate for the game loop
bounce_duration = 30  # Number of frames for the bouncing effect
num_reels = 5  # Number of reels
visible_icons = 5  # Number of visible icons per reel
bet_amount = 3
credits = 0  # Starting credits
current_win = 0
player_pool_address = "<pool_address>"

#Constants for bounce animation
BOUNCE_DISTANCE = 25  # Pixels to move down during bounce
BOUNCE_SPEED = 3      # Pixels per frame during bounce
SPIN_SPEED = 6        # Spin speed

square_size = 95  # Size of each icon
# Win thresholds for sound effects
SMALL_WIN_THRESHOLD = 20  # Play small win sound for wins up to 10 credits
BIG_WIN_THRESHOLD = 500    # Play big win sound for wins between 11 and 50 credits
# Jackpot sound will play for wins above 50 credits

# UI Positions and Sizes
BUYIN_UI_WIDTH = 500
BUYIN_UI_HEIGHT = 585
BUYIN_UI_X = (WINDOW_WIDTH - BUYIN_UI_WIDTH) // 2
BUYIN_UI_Y = (WINDOW_HEIGHT - BUYIN_UI_HEIGHT) // 2

CASHOUT_BUTTON_SIZE = (160, 50)  # Increased width for better visibility
CASHOUT_BUTTON_X = 20  # X position of the cashout button
CASHOUT_BUTTON_Y = 20  # Y position of the cashout button

bet_button_size = (30, 30)  # Smaller size for the bet button

WIN_BG_WIDTH = 200
WIN_BG_HEIGHT = 60

NEON_NUMBER_OFFSET_X = -5
NEON_NUMBER_OFFSET_Y = -3

RULES_BUTTON_SIZE = (160, 50)  # Same size as the cashout button
RULES_BUTTON_X = WINDOW_WIDTH - RULES_BUTTON_SIZE[0] - 20  # 20 pixels from the right edge
RULES_BUTTON_Y = 20  # Same Y position as the cashout button

REEL_LIGHT_WIDTH = 76
REEL_LIGHT_HEIGHT = 37
REEL_LIGHT_X = WINDOW_WIDTH - REEL_LIGHT_WIDTH - 348
REEL_LIGHT_Y = 160
REEL_LIGHT_SPACING = REEL_LIGHT_WIDTH + 31

SOUND_BUTTON_X = WINDOW_WIDTH - 70
SOUND_BUTTON_Y = WINDOW_HEIGHT - 70
WALLET_BUTTON_X = SOUND_BUTTON_X
WALLET_BUTTON_Y = SOUND_BUTTON_Y - 60

BUY_IN_BUTTON_SIZE = (200, 60)
BUY_IN_BUTTON_X = WINDOW_WIDTH // 2 - 145
BUY_IN_BUTTON_Y = WINDOW_HEIGHT - 80

# Add these new lines
BET_BUTTON_X = WINDOW_WIDTH - 435
BET_BUTTON_Y = WINDOW_HEIGHT - 70

LOADING_OVERLAY_ALPHA = 180
LOADING_TEXT_COLOR = (255, 255, 255)

# Initialize font for credits display
pygame.font.init()
font = pygame.font.Font(None, 48)
CREDITS_BG_WIDTH = 200
CREDITS_BG_HEIGHT = 60

# Surfaces and buttons
bet_button = pygame.Surface(bet_button_size, pygame.SRCALPHA)
bet_button.fill((0, 0, 0, 0))  # Fully transparent
cashout_button = pygame.Surface(CASHOUT_BUTTON_SIZE, pygame.SRCALPHA)
buy_in_button = pygame.Surface(BUY_IN_BUTTON_SIZE, pygame.SRCALPHA)
buy_in_button.fill((0, 0, 0, 0))

rules_button = pygame.Surface(RULES_BUTTON_SIZE, pygame.SRCALPHA)
pygame.draw.rect(rules_button, (0, 0, 255, 0), rules_button.get_rect())

# Reel positions and animation variables
reel_x = [
    WINDOW_WIDTH // 2 - 265,
    WINDOW_WIDTH // 2 - 150,
    WINDOW_WIDTH // 2 - 30,
    WINDOW_WIDTH // 2 + 87,
    WINDOW_WIDTH // 2 + 197
]
reel_y = [(WINDOW_HEIGHT - REEL_HEIGHT) // 2 for _ in range(num_reels)]
spinning = False  # Updated for new spin logic
bouncing = [False] * num_reels
bounce_frame = [0] * num_reels
additional_icons = [[] for _ in range(num_reels)]

# Game state variables
sound_enabled = True
sound_button = None
wallet_button = None

# Wallet variables
player_address = None
player_balance = None

# Rules screen variables
showing_rules = False
rules_image = None

# Add this near the top of the file with other global variables
buy_in_total = 0
win_differential = 0

# Add these global variables
player_pool_balance = Decimal('0')


def load_random_icons(num_icons):
    icons = []
    for _ in range(num_icons):
        icon_number = random.randint(1, 9)
        icon_path = os.path.join("data", f"reel_icon_{icon_number}.png")
        if os.path.exists(icon_path):
            icon = pygame.image.load(icon_path).convert_alpha()
            icon = pygame.transform.smoothscale(icon, (95, 95))
            icons.append(icon)
        else:
            print(f"Warning: {icon_path} not found.")
    return icons

def load_specific_icon(icon_number):
    icon_path = os.path.join("data", f"reel_icon_{icon_number}.png")
    if os.path.exists(icon_path):
        icon = pygame.image.load(icon_path).convert_alpha()
        return pygame.transform.smoothscale(icon, (95, 95))
    else:
        print(f"Warning: {icon_path} not found.")
        return None

def draw_value_display(value, x, y, width, height, text_color=(255, 255, 0)):
    value_text = font.render(f"{value}", True, text_color)
    background = pygame.Surface((width, height))
    background.fill(BLACK)
    text_rect = value_text.get_rect(center=(width // 2, height // 2))
    background.blit(value_text, text_rect)
    bg_rect = background.get_rect(topleft=(x, y))
    screen.blit(background, bg_rect)

def load_rpc_credentials(filename):
    """Load RPC credentials from a configuration file."""
    credentials = {}
    with open(filename, 'r') as file:
        for line in file:
            if line.strip() and not line.strip().startswith('['):
                parts = line.strip().split('=')
                if len(parts) == 2:
                    key = parts[0].strip().lower().replace('rpc', '')
                    credentials[key] = parts[1].strip()
    return credentials

def initialize_rpc_connection():
    # Determine the application's root directory
    if getattr(sys, 'frozen', False):
        # Running as compiled exe
        app_dir = os.path.dirname(sys.executable)
    else:
        # Running as script
        app_dir = os.path.dirname(os.path.abspath(__file__))

    # Construct the path to RPC.conf
    config_path = os.path.join(app_dir, 'RPC.conf')

    # Check if the file exists
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"RPC configuration file not found: {config_path}")

    try:
        credentials = load_rpc_credentials(config_path)
    except Exception as e:
        raise Exception(f"Failed to load RPC credentials: {str(e)}")

    rpc_user = credentials.get('user')
    rpc_password = credentials.get('password')
    rpc_host = credentials.get('host', 'localhost')
    rpc_port = credentials.get('port', '22555')

    if not all([rpc_user, rpc_password, rpc_host, rpc_port]):
        raise ValueError("Missing required RPC credentials in configuration file")

    rpc_url = f"http://{rpc_user}:{rpc_password}@{rpc_host}:{rpc_port}"
    
    try:
        return AuthServiceProxy(rpc_url)
    except Exception as e:
        raise Exception(f"Failed to establish RPC connection: {str(e)}")

def get_player_addresses_and_balances():
    print("Entering get_player_addresses_and_balances()")
    try:
        rpc_connection = initialize_rpc_connection()
        print("RPC connection initialized successfully")
        
        unspent_outputs = rpc_connection.listunspent()
        print(f"Retrieved {len(unspent_outputs)} unspent outputs")
        
        address_balances = {}
        for output in unspent_outputs:
            address = output['address']
            amount = output['amount']
            address_info = rpc_connection.validateaddress(address)
            if address_info.get('iswatchonly', False):
                print(f"Skipping watch-only address: {address}")
                continue
            if address not in address_balances:
                address_balances[address] = Decimal('0')
            address_balances[address] += Decimal(amount)
        
        addresses_and_balances = []
        for address, balance in address_balances.items():
            if balance > 1.0:
                addresses_and_balances.append((address, balance))
                print(f"Added address {address} with balance {balance}")
        
        print(f"Returning {len(addresses_and_balances)} addresses")
        return addresses_and_balances
    except JSONRPCException as e:
        print(f"JSONRPCException in get_player_addresses_and_balances: {str(e)}")
        return []
    except Exception as e:
        print(f"Unexpected error in get_player_addresses_and_balances: {str(e)}")
        return []

def wallet_ui():
    global player_address, player_balance
    manager = pygame_gui.UIManager((WINDOW_WIDTH, WINDOW_HEIGHT))
    
    print("Entering wallet_ui()")
    try:
        addresses = get_player_addresses_and_balances()
        print(f"Retrieved {len(addresses)} addresses")
        if not addresses:
            print("No addresses found or an error occurred.")
            addresses = [('No Address', Decimal('0'))]
    except Exception as e:
        print(f"An error occurred while retrieving addresses: {str(e)}")
        addresses = [('No Address', Decimal('0'))]

    address_options = [(address, f"{address} ({balance:.8f} DOGE)") for address, balance in addresses]
    print(f"Created {len(address_options)} address options for dropdown")

    dropdown = pygame_gui.elements.UIDropDownMenu(
        options_list=[option[1] for option in address_options],
        starting_option=address_options[0][1] if address_options else "No Address",
        relative_rect=pygame.Rect((WINDOW_WIDTH//2 - 200, WINDOW_HEIGHT//2 - 20), (400, 40)),
        manager=manager
    )

    submit_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((WINDOW_WIDTH//2 - 50, WINDOW_HEIGHT//2 + 50), (100, 40)),
        text="Submit",
        manager=manager
    )

    running = True
    clock = pygame.time.Clock()
    while running:
        time_delta = clock.tick(60)/1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            manager.process_events(event)
            if event.type == pygame_gui.UI_BUTTON_PRESSED:
                if event.ui_element == submit_button:
                    selected_option = dropdown.selected_option
                    print(f"Selected Option: {selected_option}")
                    selected_address = selected_option.split()[0] if isinstance(selected_option, str) else selected_option[0].split()[0]
                    print(f"Extracted Address: {selected_address}")
                    if selected_address != 'No Address':
                        player_address = selected_address
                        player_balance = next((Decimal(balance) for address, balance in addresses if address == player_address), None)
                        print(f"Updated Player Address: {player_address}")
                        print(f"Updated Player Balance: {player_balance}")
                    else:
                        print("No Address selected.")
                    running = False
        manager.update(time_delta)
        screen.fill(BLACK)
        manager.draw_ui(screen)
        pygame.display.flip()

    print("Exiting wallet_ui()")

def buyin_ui():
    global credits, screen, player_pool_address, player_address, player_balance, buy_in_total
    if player_address is None or player_balance is None:
        print("No wallet selected. Please select a wallet first.")
        show_loading_screen("Load Wallet First")
        pygame.display.flip()
        return
    print(f"Buy-in UI - Player Address: {player_address}")
    print(f"Buy-in UI - Player Balance: {player_balance}")
    BUTTON_COLORS = [
        (255, 0, 0, 128), (0, 255, 0, 128), (0, 0, 255, 128),
        (255, 255, 0, 128), (255, 0, 255, 128), (0, 255, 255, 128),
        (128, 0, 0, 128), (0, 128, 0, 128), (0, 0, 128, 128),
        (128, 128, 0, 128)
    ]
    font = pygame.font.Font(None, 36)
    button_size = (100, 100)
    button_positions = [
        (50, 100), (150, 100), (250, 100),
        (50, 200), (150, 200), (250, 200),
        (50, 300), (150, 300), (250, 300)
    ]
    number_buttons = []
    for i in range(9):
        button = pygame.Surface(button_size, pygame.SRCALPHA)
        button.fill(BUTTON_COLORS[i])
        text = font.render(str(i + 1), True, BLACK)
        text_rect = text.get_rect(center=(button_size[0] // 2, button_size[1] // 2))
        button.blit(text, text_rect)
        number_buttons.append((button, button_positions[i]))
    zero_button = pygame.Surface(button_size, pygame.SRCALPHA)
    zero_button.fill(BUTTON_COLORS[9])
    zero_text = font.render('0', True, BLACK)
    zero_text_rect = zero_text.get_rect(center=(button_size[0] // 2, button_size[1] // 2))
    zero_button.blit(zero_text, zero_text_rect)
    submit_button = pygame.Surface((140, 50), pygame.SRCALPHA)
    cancel_button = pygame.Surface((140, 50), pygame.SRCALPHA)
    submit_button.fill((0, 200, 0, 128))
    cancel_button.fill((200, 0, 0, 128))
    submit_text = font.render('Submit', True, BLACK)
    cancel_text = font.render('Cancel', True, BLACK)
    submit_button.blit(submit_text, submit_text.get_rect(center=(70, 25)))
    cancel_button.blit(cancel_text, cancel_text.get_rect(center=(70, 25)))
    running = True
    current_value = ''
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mouse_pos = pygame.mouse.get_pos()
                relative_pos = (mouse_pos[0] - BUYIN_UI_X, mouse_pos[1] - BUYIN_UI_Y)
                for i, (button, pos) in enumerate(number_buttons):
                    if pygame.Rect(pos, button_size).collidepoint(relative_pos):
                        current_value += str(i + 1)
                if pygame.Rect((150, 400), button_size).collidepoint(relative_pos):
                    current_value += '0'
                if pygame.Rect((20, 450), (140, 50)).collidepoint(relative_pos):
                    if current_value:
                        amount = int(current_value)
                        if amount > player_balance:
                            print(f"Insufficient balance. Available: {player_balance} DOGE")
                            error_text = font.render(f"Insufficient balance: {player_balance:.8f} DOGE", True, (255, 0, 0))
                            error_rect = error_text.get_rect(center=(BUYIN_UI_WIDTH // 2, BUYIN_UI_HEIGHT - 50))
                            screen.blit(error_text, error_rect)
                            pygame.display.flip()
                            pygame.time.wait(3000)
                        else:
                            try:
                                txid = process_transaction(player_address, amount)
                                if txid:
                                    credits += amount
                                    player_balance -= Decimal(amount)
                                    buy_in_total += amount  # Add the amount to buy_in_total
                                    print(f"Bought in {amount} credits! Transaction ID: {txid}")
                                    print(f"Total bought in: {buy_in_total} credits")
                                    running = False
                                else:
                                    print("Transaction failed. No credits added.")
                            except Exception as e:
                                print(f"An error occurred: {str(e)}")
                                error_text = font.render(f"Error: {str(e)}", True, (255, 0, 0))
                                error_rect = error_text.get_rect(center=(BUYIN_UI_WIDTH // 2, BUYIN_UI_HEIGHT - 50))
                                screen.blit(error_text, error_rect)
                                pygame.display.flip()
                                pygame.time.wait(3000)
                if pygame.Rect((240, 450), (140, 50)).collidepoint(relative_pos):
                    running = False
        screen.fill(BLACK)
        pygame.draw.rect(screen, WHITE, (BUYIN_UI_X, BUYIN_UI_Y, BUYIN_UI_WIDTH, BUYIN_UI_HEIGHT))
        for button, pos in number_buttons:
            screen.blit(button, (BUYIN_UI_X + pos[0], BUYIN_UI_Y + pos[1]))
        screen.blit(zero_button, (BUYIN_UI_X + 150, BUYIN_UI_Y + 400))
        pygame.draw.rect(screen, WHITE, (BUYIN_UI_X + 50, BUYIN_UI_Y + 30, 300, 50))
        display_text = font.render(current_value, True, BLACK)
        screen.blit(display_text, (BUYIN_UI_X + 60, BUYIN_UI_Y + 40))
        screen.blit(submit_button, (BUYIN_UI_X + 20, BUYIN_UI_Y + 450))
        screen.blit(cancel_button, (BUYIN_UI_X + 240, BUYIN_UI_Y + 450))
        balance_text = font.render(f"Balance: {player_balance:.8f} DOGE", True, BLACK)
        screen.blit(balance_text, (BUYIN_UI_X + 50, BUYIN_UI_Y + 500))
        pygame.display.flip()
    print(f"Current credits after buy-in: {credits}")

def show_loading_screen(text, duration=2000):
    overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, LOADING_OVERLAY_ALPHA))
    screen.blit(overlay, (0, 0))
    font = pygame.font.Font(None, 36)
    lines = text.split('\n')
    line_height = font.get_linesize()
    total_height = line_height * len(lines)
    y = (WINDOW_HEIGHT - total_height) // 2
    for line in lines:
        text_surface = font.render(line, True, LOADING_TEXT_COLOR)
        text_rect = text_surface.get_rect(center=(WINDOW_WIDTH // 2, y))
        screen.blit(text_surface, text_rect)
        y += line_height
    pygame.display.flip()
    pygame.time.wait(duration)

# Load slot layout
slot_layout_path = os.path.join("data", "slot_layout.png")
if os.path.exists(slot_layout_path):
    slot_layout = pygame.image.load(slot_layout_path).convert_alpha()
    slot_layout = pygame.transform.scale(slot_layout, (WINDOW_WIDTH, WINDOW_HEIGHT))
else:
    print(f"Warning: {slot_layout_path} not found.")
    slot_layout = None

# Load reel icons
reel_icons = [load_random_icons(visible_icons + i)[:visible_icons] for i in range(num_reels)]
reel_icons_flat = []
for icons in reel_icons:
    reel_icons_flat.extend(icons)

# Load spin button
spin_button_path = os.path.join("data", "spin_button.png")
if os.path.exists(spin_button_path):
    spin_button = pygame.image.load(spin_button_path).convert_alpha()
    spin_button = pygame.transform.smoothscale(spin_button, (100, 100))
else:
    print(f"Warning: {spin_button_path} not found.")
    spin_button = None

# Load neon number data
neon_numbers = {}
for num in [3, 6, 9]:
    neon_path = os.path.join("data", f"neon_{num}.png")
    if os.path.exists(neon_path):
        neon_numbers[num] = pygame.image.load(neon_path).convert_alpha()
        neon_numbers[num] = pygame.transform.smoothscale(neon_numbers[num], (40, 40))
    else:
        print(f"Warning: {neon_path} not found.")
        neon_numbers[num] = None

# Load the rules image
rules_image_path = os.path.join("data", "rules.png")
if os.path.exists(rules_image_path):
    rules_image = pygame.image.load(rules_image_path).convert_alpha()
    rules_image = pygame.transform.scale(rules_image, (WINDOW_WIDTH, WINDOW_HEIGHT))
else:
    print(f"Warning: {rules_image_path} not found.")

# Load reel light image
reel_light_path = os.path.join("data", "reel_light.png")
if os.path.exists(reel_light_path):
    reel_light = pygame.image.load(reel_light_path).convert_alpha()
else:
    print(f"Warning: {reel_light_path} not found.")
    reel_light = None

# Load the sound effect
soft_stop_sound = pygame.mixer.Sound(os.path.join("data", "softStop.wav"))
small_win_sound = pygame.mixer.Sound(os.path.join("data", "smallWin.wav"))
big_win_sound = pygame.mixer.Sound(os.path.join("data", "bigWin.wav"))
jackpot_sound = pygame.mixer.Sound(os.path.join("data", "jackpot.wav"))

# Load the sound button image
sound_button_path = os.path.join("data", "sound.png")
if os.path.exists(sound_button_path):
    sound_button = pygame.image.load(sound_button_path).convert_alpha()
    sound_button = pygame.transform.smoothscale(sound_button, (50, 50))
else:
    print(f"Warning: {sound_button_path} not found.")

# Load the wallet button image
wallet_button_path = os.path.join("data", "wallet.png")
if os.path.exists(wallet_button_path):
    wallet_button = pygame.image.load(wallet_button_path).convert_alpha()
    wallet_button = pygame.transform.smoothscale(wallet_button, (50, 50))
else:
    print(f"Warning: {wallet_button_path} not found.")

# REEL_X_ADJUSTMENTS for individual reel adjustments
REEL_X_ADJUSTMENTS = [15, 16, 16, 24, 16]  # Adjust these values to move reels left (-) or right (+)

# Global variables for spin animation
spinning = False
spin_result = None
result_loaded = False
spin_complete = [False] * num_reels  # num_reels is 5
result_icon_added = [False] * num_reels
random_icons_after_result = [0] * num_reels
reel_stop_counters = [0] * num_reels
bouncing = [False] * num_reels
bounce_offsets = [0] * num_reels
bounce_direction = [1] * num_reels  # 1 for down, -1 for up


# Initialize chosen_icons as a list of lists
chosen_icons = [[(random.choice(reel_icons_flat), 0) for _ in range(visible_icons)] for _ in range(num_reels)] if reel_icons_flat else []

def threaded_spin_reels():
    global spin_result
    spin_result = spin_reels()
    print("Spin result:", spin_result)

def reset_spin_variables():
    global spinning, spin_result, result_loaded, spin_complete, result_icon_added, random_icons_after_result, reel_stop_counters
    global bouncing, bounce_offsets, bounce_direction
    spinning = True
    spin_result = None
    result_loaded = False
    spin_complete = [False] * num_reels
    result_icon_added = [False] * num_reels
    random_icons_after_result = [0] * num_reels
    reel_stop_counters = [0] * num_reels
    bouncing = [False] * num_reels
    bounce_offsets = [0] * num_reels
    bounce_direction = [1] * num_reels  # 1 for down, -1 for up

def update_spin_logic(chosen_icons, square_size, SPIN_SPEED):
    """
    Updates the positions of the icons during the spinning animation.
    Manages the spinning logic, adding result icons, bouncing effect, and stopping the spin when complete.
    """
    global spinning, spin_result, result_loaded, spin_complete, result_icon_added, random_icons_after_result, reel_stop_counters
    global bouncing, bounce_offsets, bounce_direction, credits, current_win

    if spinning:
        for reel_index, reel in enumerate(chosen_icons):
            if not spin_complete[reel_index]:
                if not bouncing[reel_index]:
                    # Regular spinning logic
                    for i, (icon, offset) in enumerate(reel):
                        # Move the icon down by SPIN_SPEED pixels
                        chosen_icons[reel_index][i] = (icon, offset + SPIN_SPEED)

                    if chosen_icons[reel_index][0][1] >= square_size:
                        # Remove the icon that has moved off-screen
                        chosen_icons[reel_index].pop()

                        # Define the number of extra spins for each reel
                        extra_spins = [0, 1, 2, 3, 4]

                        if spin_result and reel_stop_counters[reel_index] >= extra_spins[reel_index]:
                            if not result_icon_added[reel_index]:
                                # Add the result icon for this reel
                                new_icon_path = os.path.join("data", spin_result[reel_index])
                                if os.path.exists(new_icon_path):
                                    new_icon = pygame.image.load(new_icon_path).convert_alpha()
                                    new_icon = pygame.transform.smoothscale(new_icon, (95, 95))
                                    chosen_icons[reel_index].insert(0, (new_icon, 0))
                                    result_icon_added[reel_index] = True
                                else:
                                    # If the result icon is not found, add a random icon
                                    print(f"Error: Icon file not found - {new_icon_path}")
                                    new_icon = random.choice(reel_icons_flat)
                                    chosen_icons[reel_index].insert(0, (new_icon, 0))
                            else:
                                # Add a random icon to the top of the reel
                                new_icon = random.choice(reel_icons_flat)
                                chosen_icons[reel_index].insert(0, (new_icon, 0))
                                random_icons_after_result[reel_index] += 1

                                # Check if the reel has completed spinning
                                if random_icons_after_result[reel_index] >= 2:
                                    # Start bouncing effect
                                    bouncing[reel_index] = True
                                    if sound_enabled:
                                        soft_stop_sound.play()
                                    print(f"Reel {reel_index + 1} started bouncing!")
                        else:
                            # Add a random icon to the top of the reel
                            new_icon = random.choice(reel_icons_flat)
                            chosen_icons[reel_index].insert(0, (new_icon, 0))
                            if spin_result:
                                reel_stop_counters[reel_index] += 1

                        # Adjust positions of remaining icons
                        for i in range(1, len(chosen_icons[reel_index])):
                            chosen_icons[reel_index][i] = (chosen_icons[reel_index][i][0], chosen_icons[reel_index][i][1] - square_size)
                else:
                    # Bouncing logic
                    if bounce_direction[reel_index] == 1:  # Moving down
                        bounce_offsets[reel_index] += BOUNCE_SPEED
                        if bounce_offsets[reel_index] >= BOUNCE_DISTANCE:
                            bounce_offsets[reel_index] = BOUNCE_DISTANCE
                            bounce_direction[reel_index] = -1
                    elif bounce_direction[reel_index] == -1:  # Moving up
                        bounce_offsets[reel_index] -= BOUNCE_SPEED
                        if bounce_offsets[reel_index] <= 0:
                            bounce_offsets[reel_index] = 0
                            bouncing[reel_index] = False
                            spin_complete[reel_index] = True
                            print(f"Spin complete for reel {reel_index + 1}! Bouncing finished.")

        # If all reels have completed spinning, stop the spinning
        if all(spin_complete):
            spinning = False
            print("All reels have completed spinning!")
            # Calculate win after spin is complete
            if spin_result:
                win, win_type = win_calculator.calculate_win(spin_result, bet_amount, credits)
                print(f"Debug: Win calculated - Amount: {win}, Type: {win_type}")
                if sound_enabled:
                    if 0 < win <= SMALL_WIN_THRESHOLD:
                        print("Debug: Playing small win sound")
                        small_win_sound.play()
                    elif SMALL_WIN_THRESHOLD < win <= BIG_WIN_THRESHOLD:
                        print("Debug: Playing big win sound")
                        big_win_sound.play()
                    elif win > BIG_WIN_THRESHOLD:
                        print("Debug: Playing jackpot sound")
                        jackpot_sound.play()
                current_win = win
                credits += win  # Add the win to the credits
                print(f"Spin Result: {spin_result}, Bet Amount: {bet_amount}, Win: {win}, Win Type: {win_type}, Credits: {credits}")
                spin_result = None

def draw_icons(screen, chosen_icons, start_x, start_y, square_size):
    """
    Draws the icons on the screen at their current positions.
    Applies bounce offsets if reels are bouncing.
    """
    for reel_index, reel in enumerate(chosen_icons):
        for i, (icon, offset) in enumerate(reel):
            x = start_x + reel_index * (square_size + 20) + REEL_X_ADJUSTMENTS[reel_index]  # Add individual reel adjustment
            y = start_y + i * square_size + offset + bounce_offsets[reel_index]
            screen.blit(icon, (x, y))

def calculate_reel_positions(square_size, num_squares):
    """
    Calculates the starting positions for the reels and returns them.
    """
    total_height = num_squares * square_size
    start_y = (WINDOW_HEIGHT - total_height) // 2

    # Calculate the total width of all reels and spacing
    total_width = (square_size * num_reels) + (20 * (num_reels - 1))  # num_reels reels with 20px spacing between them
    start_x = (WINDOW_WIDTH - total_width) // 2  # Center all reels

    # Adjust start_x if needed
    return start_x, start_y

def import_watch_only_address(rpc_connection, address):
    try:
        rpc_connection.importaddress(address, "player_pool", False)
        print(f"Successfully imported watch-only address: {address}")
    except JSONRPCException as e:
        print(f"Error importing watch-only address: {str(e)}")

# Add this function near the top of your file, after the imports and global variables
def initialize_game():
    global player_pool_address
    
    try:
        rpc_connection = initialize_rpc_connection()
        import_watch_only_address(rpc_connection, player_pool_address)
        update_player_pool_balance()  # Add this line
    except Exception as e:
        print(f"Error initializing game: {str(e)}")

# Add this function to update the player pool balance
def update_player_pool_balance():
    global player_pool_balance
    try:
        rpc_connection = initialize_rpc_connection()
        unspent_outputs = rpc_connection.listunspent(0, 9999999, [player_pool_address])
        total_balance = sum(Decimal(output['amount']) for output in unspent_outputs)
        print(f"Raw balance from listunspent: {total_balance}")
        player_pool_balance = total_balance.quantize(Decimal('1.'), rounding=ROUND_HALF_UP)
        print(f"Rounded player pool balance: {player_pool_balance}")
    except Exception as e:
        print(f"Error updating player pool balance: {str(e)}")


# Add this function to draw the player pool balance
def draw_player_pool_balance():
    balance_font = pygame.font.Font(None, 36)
    balance_text = f"Player Pool: {player_pool_balance} DOGE"
    balance_surface = balance_font.render(balance_text, True, WHITE)
    balance_rect = balance_surface.get_rect(midtop=(WINDOW_WIDTH // 2, 80))
    screen.blit(balance_surface, balance_rect)

# Main game loop
clock = pygame.time.Clock()
running = True
spin_result = None

# Display the loading screen with the warning message
show_loading_screen("Play at your own risk.\nMalfunctions void all payouts.")

# Initialize the game
initialize_game()

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if showing_rules:
                showing_rules = False
            elif not spinning:
                if rules_button.get_rect(topleft=(RULES_BUTTON_X, RULES_BUTTON_Y)).collidepoint(event.pos):
                    showing_rules = True
                elif spin_button and spin_button.get_rect(topleft=(270, WINDOW_HEIGHT - 100)).collidepoint(event.pos):
                    if credits >= bet_amount:
                        credits -= bet_amount  # Subtract bet amount only once, when spinning starts
                        reset_spin_variables()
                        threading.Thread(target=threaded_spin_reels).start()
                elif bet_button.get_rect(topleft=(BET_BUTTON_X, BET_BUTTON_Y)).collidepoint(event.pos):
                    if bet_amount == 3:
                        bet_amount = 6
                    elif bet_amount == 6:
                        bet_amount = 9
                    else:
                        bet_amount = 3
                    print(f"Bet amount changed to: {bet_amount}")
                elif cashout_button.get_rect(topleft=(CASHOUT_BUTTON_X, CASHOUT_BUTTON_Y)).collidepoint(event.pos):
                    print("Cashout button clicked!")
                    if player_address is None:
                        show_loading_screen("Load Wallet First")
                    elif credits > 0:
                        recipient_address = player_address
                        amount_to_send = credits
                        win_differential = amount_to_send - buy_in_total
                        txid = send_doge(recipient_address, amount_to_send, win_differential)
                        if txid:
                            print(f"Cashout successful! TXID: {txid}")
                            print(f"Amount cashed out: {amount_to_send} DOGE")
                            print(f"Total bought in: {buy_in_total} DOGE")
                            print(f"Win Differential: {win_differential} DOGE")
                            credits = 0
                            buy_in_total = 0  # Reset buy_in_total after cashout
                            win_differential = 0  # Reset win_differential after cashout
                        else:
                            print("Cashout failed. Please try again.")
                    else:
                        print("No credits to cash out.")
                if sound_button and sound_button.get_rect(topleft=(SOUND_BUTTON_X, SOUND_BUTTON_Y)).collidepoint(event.pos):
                    sound_enabled = not sound_enabled
                    print(f"Sound {'enabled' if sound_enabled else 'disabled'}")
                elif buy_in_button.get_rect(topleft=(BUY_IN_BUTTON_X, BUY_IN_BUTTON_Y)).collidepoint(event.pos):
                    buyin_ui()
                    print(f"Current credits after buy-in: {credits}")
                    print(f"Total bought in: {buy_in_total} credits")
                if wallet_button and wallet_button.get_rect(topleft=(WALLET_BUTTON_X, WALLET_BUTTON_Y)).collidepoint(event.pos):
                    print("Wallet button clicked!")
                    show_loading_screen("Loading Wallets...")
                    pygame.display.flip()
                    wallet_ui()
                    if player_address is not None and player_balance is not None:
                        print(f"Wallet selected: {player_address}")
                        print(f"Balance: {player_balance}")
                    else:
                        print("Wallet selection cancelled or failed.")
    screen.fill(BLACK)
    if showing_rules:
        if rules_image:
            screen.blit(rules_image, (0, 0))
    else:
        # Update spinning logic
        update_spin_logic(chosen_icons, square_size, SPIN_SPEED)

        # Calculate reel positions
        num_squares = visible_icons
        start_x, start_y = calculate_reel_positions(square_size, num_squares)

        # Draw icons
        draw_icons(screen, chosen_icons, start_x, start_y, square_size)

        # Overlay for reels based on bet amount
        overlay = pygame.Surface((REEL_WIDTH, REEL_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, REEL_OVERLAY_ALPHA))
        if bet_amount == 3:
            screen.blit(overlay, (reel_x[3], (WINDOW_HEIGHT - REEL_HEIGHT) // 2))
            screen.blit(overlay, (reel_x[4], (WINDOW_HEIGHT - REEL_HEIGHT) // 2))
        elif bet_amount == 6:
            screen.blit(overlay, (reel_x[4], (WINDOW_HEIGHT - REEL_HEIGHT) // 2))

        # Draw credits display
        draw_value_display(credits, WINDOW_WIDTH // 2 - 145, WINDOW_HEIGHT - 80, CREDITS_BG_WIDTH, CREDITS_BG_HEIGHT)

        # Draw win display
        win_display_x = BET_BUTTON_X + bet_button_size[0] + 10
        draw_value_display(current_win, win_display_x, WINDOW_HEIGHT - 80, WIN_BG_WIDTH, WIN_BG_HEIGHT, text_color=(0, 255, 0))

        # Draw bet amount neon numbers
        if neon_numbers[bet_amount]:
            neon_number_x = BET_BUTTON_X + NEON_NUMBER_OFFSET_X
            neon_number_y = BET_BUTTON_Y + NEON_NUMBER_OFFSET_Y
            screen.blit(neon_numbers[bet_amount], (neon_number_x, neon_number_y))

        # Draw slot layout
        if slot_layout:
            screen.blit(slot_layout, (0, 0))

        # Draw remaining UI elements
        screen.blit(bet_button, (BET_BUTTON_X, BET_BUTTON_Y))  # This is now transparent
        screen.blit(buy_in_button, (BUY_IN_BUTTON_X, BUY_IN_BUTTON_Y))
        if reel_light:
            if bet_amount >= 6:
                screen.blit(reel_light, (REEL_LIGHT_X, REEL_LIGHT_Y))
            if bet_amount == 9:
                screen.blit(reel_light, (REEL_LIGHT_X + REEL_LIGHT_SPACING, REEL_LIGHT_Y))
        if spin_button:
            screen.blit(spin_button, (270, WINDOW_HEIGHT - 100))
        screen.blit(cashout_button, (CASHOUT_BUTTON_X, CASHOUT_BUTTON_Y))
        screen.blit(rules_button, (RULES_BUTTON_X, RULES_BUTTON_Y))
        if sound_button:
            screen.blit(sound_button, (SOUND_BUTTON_X, SOUND_BUTTON_Y))
            if not sound_enabled:
                pygame.draw.line(screen, (255, 0, 0), (SOUND_BUTTON_X, SOUND_BUTTON_Y), 
                                 (SOUND_BUTTON_X + 50, SOUND_BUTTON_Y + 50), 3)
                pygame.draw.line(screen, (255, 0, 0), (SOUND_BUTTON_X + 50, SOUND_BUTTON_Y), 
                                 (SOUND_BUTTON_X, SOUND_BUTTON_Y + 50), 3)
        if wallet_button:
            screen.blit(wallet_button, (WALLET_BUTTON_X, WALLET_BUTTON_Y))

        # Add this line to draw the player pool balance
        draw_player_pool_balance()

    pygame.display.flip()
    clock.tick(frame_rate)

    # Add this line to update the player pool balance periodically
    if pygame.time.get_ticks() % 60000 < 100:  # Update roughly every minute
        update_player_pool_balance()

pygame.mixer.quit()
pygame.quit()