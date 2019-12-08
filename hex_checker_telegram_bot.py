import time
import schedule
import sys
import signal
from datetime import datetime
from threading import Thread
import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

from hex_info import HexInfo

class Bot:

	# ------------ Config ------------ #
	
	# your chat_id
	_CHAT_ID = "YOUR_CHAT_ID"
	# your telegram token
	_TOKEN = "YOUR_TELEGRAM_TOKEN"
	# your user whitelist (leave empty if no check are necessary)
	_USER_WHITELIST = ["YOUR_TELEGRAM_USERNAME"]
	# allow only specific type of chats
	_HANDLED_CHATS = ["private"]
	# number of lobbies to use to compage sizes
	_COMPARED_LOWEST_LOBBY_SIZES = 3
	# time of the daily telegram notification (HH:MM:SS in local time)
	_NOTIFICATION_LOCAL_24h_TIME = "00:00:25"
	
	# ------------ ------ ------------ #

	START_TIME = time.time()
	HEX_INFO = None
	
	def __init__(self, hex_info):
		Bot.HEX_INFO = hex_info
		self.telegram_api = telegram.Bot(token=Bot._TOKEN)
		self.telegram_updater = Updater(token=Bot._TOKEN)
		self._register_handlers()

		
	def send_message(self, content, markdown=True):
		kwargs = {}
		if markdown:
			kwargs["parse_mode"] = telegram.parsemode.ParseMode.MARKDOWN
		try:
			if content:
				self.telegram_api.send_message(chat_id=Bot._CHAT_ID, text=content, **kwargs)
		except telegram.error.TimedOut:
			# retry on failing
			try:
				self.telegram_api.send_message(chat_id=Bot._CHAT_ID, text=content, **kwargs)
			except telegram.error.TimedOut as e:
				print(f"Error: failed to send message : {e}")
		except telegram.error.Unauthorized as e:
			print(f"Error: failed to send message ({e}): invalid telegram configuration.")
			
	def send_info(self):
		self.send_message(self._get_info_message())
			
	def start(self):
		print("Launching Hex info Telegram bot")
		self.telegram_updater.start_polling()
		
	def stop(self):
		print("Stopping Telegram bot ...")
		self.telegram_updater.stop()
	
	def _register_handlers(self):
		self.telegram_updater.dispatcher.add_error_handler(self._error_handler)
		self.telegram_updater.dispatcher.add_handler(MessageHandler(Filters.text, self._echo))

		for handler in self._get_handlers():
			self.telegram_updater.dispatcher.add_handler(handler)
			
	def _get_handlers(self):
		return [
			CommandHandler("start", self._command_start),
			CommandHandler("ping", self._command_ping),
			CommandHandler("info", self._command_info),
			CommandHandler("help", self._command_help),
			MessageHandler(Filters.command, self._command_unknown)
		]
	
	@staticmethod
	def _command_start(_, update):
		if Bot._is_valid_request(update):
			update.message.reply_markdown("Hello, I'm the Hex info Bot. I will update you before the "
			"end of each adoption amplifier lobby.\nType /info to get the current lobby info.\nType "
			"/help to get help about my skills.")
		else:
			update.message.reply_markdown(update, "Nope")
	
	@staticmethod
	def _command_info(_, update):
		if Bot._is_valid_request(update):
			Bot.HEX_INFO.refresh_data()
			update.message.reply_markdown(Bot._get_info_message())
	
	@staticmethod
	def _command_ping(_, update):
		if Bot._is_valid_request(update):
			update.message.reply_markdown(
				f"I'm alive since {datetime.fromtimestamp(Bot.START_TIME).strftime('%Y-%m-%d %H:%M:%S')}.")
	
	@staticmethod
	def _command_help(_, update):
		if Bot._is_valid_request(update):
			message = "* - My Hex info Bot skills - *\n\n"
			message += "/start: `Displays my startup message.`\n"
			message += "/ping: `Shows for how long I'm working.`\n"
			message += "/info: `Shows Hex useful info.`\n"
			message += "/help: `Shows this help.`"
			update.message.reply_markdown(message)


	@staticmethod
	def _command_unknown(_, update):
		if Bot._is_valid_request(update):
			update.message.reply_text(f"Unfortunately, I don't know the command: {update.effective_message.text}.")

	@staticmethod
	def _echo(_, update):
		if Bot._is_valid_request(update):
			update.message.reply_text(update.effective_message["text"])

	@staticmethod
	def _error_handler(_, update, error):
		update.message.reply_markdown(f"Failed to perform this command error: `{error}`")
	
	@staticmethod
	def _is_valid_request(update):
		user_name =update.effective_chat["username"]
		return update.effective_chat["type"] in Bot._HANDLED_CHATS and \
			(not Bot._USER_WHITELIST or user_name in Bot._USER_WHITELIST or f"@{user_name}" in Bot._USER_WHITELIST)
	
	@staticmethod
	def _get_info_message():
		message = "* - Today's lobby info - *\n\n"
		message += f"Adoption amplifier day: *{Bot.HEX_INFO.current_day}*\n\n"
		message += f"Lobby size: `{round(Bot.HEX_INFO.get_current_day_lobby_eth_size(), 3)} ETH`\n"
		if Bot.HEX_INFO.is_lowest_lobby_size():
			message += f"- *Today is the smallest lobby size so far !*\n"
		elif Bot.HEX_INFO.is_in_lowest_lobby_sizes(Bot._COMPARED_LOWEST_LOBBY_SIZES):
			message += f"*- Today is within the {Bot._COMPARED_LOWEST_LOBBY_SIZES} smallest lobby sizes so far !*\n"
		else:
			message += "- Today is not one of the smallest lobby days\n"
		historical_lobbies = Bot.HEX_INFO.get_lowest_historical_lobbies_sizes(Bot._COMPARED_LOWEST_LOBBY_SIZES)
		str_lobbies = [str(round(HexInfo.wei_to_eth(h), 3)) for h in historical_lobbies]
		message += f"Smallest lobby sizes: *{', '.join(str_lobbies)} ETH*\n\n"
			
		message += f"Stacked percent: `{round(Bot.HEX_INFO.get_stacked_ratio() * 100, 3)}%`\n"
		message += f"Circulating supply: `{round(HexInfo.heart_to_hex(Bot.HEX_INFO.circulating_supply) / 1e6, 6)} million Hex`\n"
		message += f"Total supply: `{round(HexInfo.heart_to_hex(Bot.HEX_INFO.total_supply) / 1e6, 6)} million HEX`"
		return message
		

hex = HexInfo()
bot = Bot(hex)
keep_running = True
	
	
def refresh_and_send_info():
	print(f"Info message sent at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
	hex.refresh_data()
	bot.send_info()
	
	
def start_scheduler():
	schedule.every().day.at(Bot._NOTIFICATION_LOCAL_24h_TIME).do(refresh_and_send_info)
	while keep_running:
		schedule.run_pending()
		time.sleep(5)
		
if __name__ == "__main__":
	def signal_handler(sig, frame):
		global keep_running
		keep_running = False
		bot.stop()
	signal.signal(signal.SIGINT, signal_handler)

	Thread(bot.start()).start()
	bot.send_message("*Hex info Telegram Bot online !*")
	bot.send_info()

	start_scheduler()
	