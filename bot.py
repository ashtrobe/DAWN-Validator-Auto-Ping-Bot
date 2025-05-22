import requests
from fake_useragent import FakeUserAgent
from datetime import datetime
from colorama import *
import asyncio, json, os, pytz, uuid
import re
from pathlib import Path
from typing import Literal, TypedDict, Union
from pydantic import BaseModel, Field, field_validator
from pydantic.networks import HttpUrl, IPv4Address
from requests.exceptions import ProxyError, SSLError

wib = pytz.timezone('Asia/Jakarta')

# Proxy parsing logic
Protocol = Literal["http", "https", "socks4", "socks5"]
PROXY_FORMATS_REGEXP = [
    re.compile(
        r"^(?:(?P<protocol>.+)://)?"  # Optional: protocol
        r"(?P<login>[^@:]+)"  # Login (no ':' or '@')
        r":(?P<password>[^@]+)"  # Password (can contain ':', but not '@')
        r"[@:]"  # '@' or ':' as separator
        r"(?P<host>[^@:\s]+)"  # Host (no ':' or '@')
        r":(?P<port>\d{1,5})"  # Port: 1 to 5 digits
        r"(?:\[(?P<refresh_url>https?://[^\s\]]+)\])?$"  # Optional: [refresh_url]
    ),
    re.compile(
        r"^(?:(?P<protocol>.+)://)?"  # Optional: protocol
        r"(?P<host>[^@:\s]+)"  # Host (no ':' or '@')
        r":(?P<port>\d{1,5})"  # Port: 1 to 5 digits
        r"[@:]"  # '@' or ':' as separator
        r"(?P<login>[^@:]+)"  # Login (no ':' or '@')
        r":(?P<password>[^@]+)"  # Password (can contain ':', but not '@')
        r"(?:\[(?P<refresh_url>https?://[^\s\]]+)\])?$"  # Optional: [refresh_url]
    ),
    re.compile(
        r"^(?:(?P<protocol>.+)://)?"  # Optional: protocol
        r"(?P<host>[^@:\s]+)"  # Host (no ':' or '@')
        r":(?P<port>\d{1,5})"  # Port: 1 to 5 digits
        r"(?:\[(?P<refresh_url>https?://[^\s\]]+)\])?$"  # Optional: [refresh_url]
    ),
]

class ParsedProxy(TypedDict):
    host: str
    port: int
    protocol: Protocol | None
    login: str | None
    password: str | None
    refresh_url: str | None

def parse_proxy_str(proxy: str) -> ParsedProxy:
    if not proxy:
        raise ValueError(f"Proxy cannot be an empty string")
    for pattern in PROXY_FORMATS_REGEXP:
        match = pattern.match(proxy)
        if match:
            groups = match.groupdict()
            return {
                "host": groups["host"],
                "port": int(groups["port"]),
                "protocol": groups.get("protocol"),
                "login": groups.get("login"),
                "password": groups.get("password"),
                "refresh_url": groups.get("refresh_url"),
            }
    raise ValueError(f"Unsupported proxy format: '{proxy}'")

def _load_lines(filepath: Path | str) -> list[str]:
    with open(filepath, "r") as file:
        return [line.strip() for line in file.readlines() if line.strip()]

class Proxy(BaseModel):
    host: str
    port: int = Field(gt=0, le=65535)
    protocol: Protocol = "http"
    login: str | None = None
    password: str | None = None
    refresh_url: str | None = None

    @field_validator("host")
    def host_validator(cls, v):
        if v.replace(".", "").isdigit():
            IPv4Address(v)
        else:
            HttpUrl(f"http://{v}")
        return v

    @field_validator("refresh_url")
    def refresh_url_validator(cls, v):
        if v:
            HttpUrl(v)
        return v

    @field_validator("protocol")
    def protocol_validator(cls, v):
        if v not in ["http", "https", "socks4", "socks5"]:
            raise ValueError("Only http, https, socks4, and socks5 protocols are supported")
        return v

    @classmethod
    def from_str(cls, proxy: Union[str, "Proxy"]) -> "Proxy":
        if proxy is None:
            raise ValueError("Proxy cannot be None")
        if isinstance(proxy, cls):
            return proxy
        parsed_proxy = parse_proxy_str(proxy)
        parsed_proxy["protocol"] = parsed_proxy["protocol"] or "http"
        return cls(**parsed_proxy)

    @classmethod
    def from_file(cls, filepath: Path | str) -> list["Proxy"]:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Proxy file not found: {filepath}")
        proxies = []
        for proxy in _load_lines(path):
            try:
                proxy_obj = cls.from_str(proxy)
                # Force http for https proxies to avoid SSL issues, keep socks intact
                if proxy_obj.protocol == "https":
                    proxy_obj.protocol = "http"
                proxies.append(proxy_obj)
            except ValueError as e:
                print(f"{Fore.RED + Style.BRIGHT}✗ Invalid proxy format: {proxy} ({e}){Style.RESET_ALL}")
        return proxies

    @property
    def as_url(self) -> str:
        return (
            f"{self.protocol}://"
            + (f"{self.login}:{self.password}@" if self.login and self.password else "")
            + f"{self.host}:{self.port}"
        )

    @property
    def as_proxies_dict(self) -> dict:
        proxies = {}
        proxies["http"] = self.as_url
        proxies["https"] = self.as_url
        return proxies

class Dawn:
    def __init__(self) -> None:
        self.headers = {
            "Accept": "*/*",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            "Origin": "chrome-extension://fpdkjdnhkakefebpekbdhillbhonfjjp",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "User-Agent": FakeUserAgent().random
        }
        self.BASE_API = "https://ext-api.dawninternet.com"
        self.proxies = []
        self.proxy_index = 0
        self.account_proxies = {}

    def clear_terminal(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def log(self, message):
        print(
            f"{Fore.CYAN + Style.BRIGHT}╭─[{datetime.now().astimezone(wib).strftime('%x %X %Z')}]{Style.RESET_ALL}\n"
            f"{Fore.CYAN + Style.BRIGHT}╰──▶{Style.RESET_ALL} {message}",
            flush=True
        )

    def welcome(self):
        print(
            f"""{Fore.BLUE + Style.BRIGHT}
   ██████╗  █████╗ ██╗    ██╗███╗   ██╗
   ██╔══██╗██╔══██╗██║    ██║████╗  ██║
   ██║  ██║███████║██║ █╗ ██║██╔██╗ ██║
   ██║  ██║██╔══██║██║███╗██║██║╚██╗██║
   ██████╔╝██║  ██║╚███╔███╔╝██║ ╚████║
   ╚═════╝ ╚═╝  ╚═╝ ╚══╝╚══╝ ╚═╝  ╚═══╝
            {Fore.GREEN + Style.BRIGHT}AUTO PING BOT thanks to ashtrobe for script  menu by ansh {Style.RESET_ALL}
            """
        )

    def format_seconds(self, seconds):
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

    def load_accounts(self):
        filename = "accounts.json"
        try:
            if not os.path.exists(filename):
                self.log(f"{Fore.RED}✗ File {filename} not found, creating empty file{Style.RESET_ALL}")
                with open(filename, 'w') as file:
                    json.dump([], file)
                return []
            with open(filename, 'r') as file:
                data = json.load(file)
                if isinstance(data, list):
                    return data
                return []
        except json.JSONDecodeError:
            self.log(f"{Fore.RED}✗ Invalid JSON in {filename}, resetting to empty{Style.RESET_ALL}")
            with open(filename, 'w') as file:
                json.dump([], file)
            return []

    def save_accounts(self, accounts):
        filename = "accounts.json"
        try:
            with open(filename, 'w') as file:
                json.dump(accounts, file, indent=4)
            self.log(f"{Fore.GREEN}✓ Accounts saved to {filename}{Style.RESET_ALL}")
        except Exception as e:
            self.log(f"{Fore.RED}✗ Failed to save accounts: {e}{Style.RESET_ALL}")

    async def load_proxies(self, use_proxy_choice: int):
        filename = "proxy.txt"
        try:
            if use_proxy_choice == 1:
                response = requests.get("https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/all.txt")
                response.raise_for_status()
                content = response.text
                with open(filename, 'w') as file:
                    file.write(content)
            self.proxies = Proxy.from_file(filename)

            if not self.proxies:
                self.log(f"{Fore.RED + Style.BRIGHT}✗ No proxies found{Style.RESET_ALL}")
                return

            self.log(
                f"{Fore.GREEN + Style.BRIGHT}✓ Proxies loaded: {Style.RESET_ALL}"
                f"{Fore.WHITE + Style.BRIGHT}{len(self.proxies)}{Style.RESET_ALL}"
            )

        except Exception as e:
            self.log(f"{Fore.RED + Style.BRIGHT}✗ Proxy load failed: {e}{Style.RESET_ALL}")
            self.proxies = []

    def get_next_proxy_for_account(self, email):
        if email not in self.account_proxies:
            if not self.proxies:
                return None
            proxy = self.proxies[self.proxy_index]
            self.account_proxies[email] = proxy
            self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return self.account_proxies[email]

    def rotate_proxy_for_account(self, email):
        if not self.proxies:
            return None
        proxy = self.proxies[self.proxy_index]
        self.account_proxies[email] = proxy
        self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return proxy

    def generate_app_id(self):
        prefix = "67"
        app_id = prefix + uuid.uuid4().hex[len(prefix):]
        return app_id

    def mask_account(self, account):
        if "@" in account:
            local, domain = account.split('@', 1)
            mask_account = local[:3] + '*' * 3 + local[-3:] if len(local) > 6 else local[:1] + '*' * (len(local)-2) + local[-1:]
            return f"{mask_account}@{domain}"
        mask_account = account[:3] + '*' * 3 + account[-3:] if len(account) > 6 else account[:1] + '*' * (len(account)-2) + account[-1:]
        return mask_account

    def print_message(self, email, proxy, color, message):
        proxy_str = proxy.as_url if proxy else 'No Proxy'
        self.log(
            f"{Fore.MAGENTA + Style.BRIGHT}Account:{Style.RESET_ALL} "
            f"{Fore.CYAN + Style.BRIGHT}{self.mask_account(email)}{Style.RESET_ALL} | "
            f"{Fore.MAGENTA + Style.BRIGHT}Proxy:{Style.RESET_ALL} "
            f"{Fore.CYAN + Style.BRIGHT}{proxy_str}{Style.RESET_ALL}\n"
            f"{Fore.MAGENTA + Style.BRIGHT}Status:{Style.RESET_ALL} "
            f"{color + Style.BRIGHT}{message}{Style.RESET_ALL}"
        )

    def print_question(self):
        while True:
            try:
                print(f"{Fore.YELLOW + Style.BRIGHT}Proxy Options:{Style.RESET_ALL}")
                print(f"{Fore.GREEN + Style.BRIGHT}1. {Fore.CYAN}Use Monosans Proxy{Style.RESET_ALL}")
                print(f"{Fore.GREEN + Style.BRIGHT}2. {Fore.CYAN}Use Private Proxy{Style.RESET_ALL}")
                print(f"{Fore.GREEN + Style.BRIGHT}3. {Fore.CYAN}No Proxy{Style.RESET_ALL}")
                choose = int(input(f"{Fore.YELLOW + Style.BRIGHT}Select option [1/2/3]: {Style.RESET_ALL}").strip())
                if choose in [1, 2, 3]:
                    proxy_type = (
                        "Monosans Proxy" if choose == 1 else
                        "Private Proxy" if choose == 2 else
                        "No Proxy"
                    )
                    print(f"{Fore.GREEN + Style.BRIGHT}✓ Selected: {proxy_type}{Style.RESET_ALL}")
                    return choose
                else:
                    print(f"{Fore.RED + Style.BRIGHT}✗ Invalid option. Choose 1, 2 or 3{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED + Style.BRIGHT}✗ Invalid input. Enter a number{Style.RESET_ALL}")

    def display_accounts(self):
        accounts = self.load_accounts()
        if not accounts:
            self.log(f"{Fore.YELLOW}No accounts found in accounts.json{Style.RESET_ALL}")
            return
        self.log(f"{Fore.CYAN}Current Accounts:{Style.RESET_ALL}")
        for i, account in enumerate(accounts, 1):
            email = account.get('Email', 'N/A')
            token = account.get('Token', 'N/A')[:5] + '...' if account.get('Token') else 'N/A'
            print(f"{Fore.GREEN + Style.BRIGHT}{i}. {Fore.CYAN}Email: {self.mask_account(email)} | Token: {token}{Style.RESET_ALL}")

    def add_account(self):
        email = input(f"{Fore.YELLOW + Style.BRIGHT}Enter email: {Style.RESET_ALL}").strip()
        if not email or '@' not in email:
            self.log(f"{Fore.RED}✗ Invalid email format{Style.RESET_ALL}")
            return
        token = input(f"{Fore.YELLOW + Style.BRIGHT}Enter token: {Style.RESET_ALL}").strip()
        if not token:
            self.log(f"{Fore.RED}✗ Token cannot be empty{Style.RESET_ALL}")
            return
        accounts = self.load_accounts()
        accounts.append({"Email": email, "Token": token})
        self.save_accounts(accounts)
        self.log(f"{Fore.GREEN}✓ Account added: {self.mask_account(email)}{Style.RESET_ALL}")

    def edit_account(self):
        accounts = self.load_accounts()
        if not accounts:
            self.log(f"{Fore.YELLOW}No accounts to edit{Style.RESET_ALL}")
            return
        self.display_accounts()
        try:
            index = int(input(f"{Fore.YELLOW + Style.BRIGHT}Select account number to edit (1-{len(accounts)}): {Style.RESET_ALL}").strip()) - 1
            if index < 0 or index >= len(accounts):
                self.log(f"{Fore.RED}✗ Invalid account number{Style.RESET_ALL}")
                return
            email = input(f"{Fore.YELLOW + Style.BRIGHT}Enter new email (leave blank to keep {self.mask_account(accounts[index]['Email'])}): {Style.RESET_ALL}").strip()
            token = input(f"{Fore.YELLOW + Style.BRIGHT}Enter new token (leave blank to keep current): {Style.RESET_ALL}").strip()
            if email:
                if '@' not in email:
                    self.log(f"{Fore.RED}✗ Invalid email format{Style.RESET_ALL}")
                    return
                accounts[index]["Email"] = email
            if token:
                accounts[index]["Token"] = token
            self.save_accounts(accounts)
            self.log(f"{Fore.GREEN}✓ Account updated: {self.mask_account(accounts[index]['Email'])}{Style.RESET_ALL}")
        except ValueError:
            self.log(f"{Fore.RED}✗ Invalid input. Enter a number{Style.RESET_ALL}")

    def delete_account(self):
        accounts = self.load_accounts()
        if not accounts:
            self.log(f"{Fore.YELLOW}No accounts to delete{Style.RESET_ALL}")
            return
        self.display_accounts()
        try:
            index = int(input(f"{Fore.YELLOW + Style.BRIGHT}Select account number to delete (1-{len(accounts)}): {Style.RESET_ALL}").strip()) - 1
            if index < 0 or index >= len(accounts):
                self.log(f"{Fore.RED}✗ Invalid account number{Style.RESET_ALL}")
                return
            email = accounts[index]['Email']
            del accounts[index]
            self.save_accounts(accounts)
            self.log(f"{Fore.GREEN}✓ Account deleted: {self.mask_account(email)}{Style.RESET_ALL}")
        except ValueError:
            self.log(f"{Fore.RED}✗ Invalid input. Enter a number{Style.RESET_ALL}")

    def accounts_menu(self):
        while True:
            self.clear_terminal()
            self.welcome()
            self.log(f"{Fore.YELLOW + Style.BRIGHT}Accounts Menu:{Style.RESET_ALL}")
            print(f"{Fore.GREEN + Style.BRIGHT}1. {Fore.CYAN}View Accounts{Style.RESET_ALL}")
            print(f"{Fore.GREEN + Style.BRIGHT}2. {Fore.CYAN}Add Account{Style.RESET_ALL}")
            print(f"{Fore.GREEN + Style.BRIGHT}3. {Fore.CYAN}Edit Account{Style.RESET_ALL}")
            print(f"{Fore.GREEN + Style.BRIGHT}4. {Fore.CYAN}Delete Account{Style.RESET_ALL}")
            print(f"{Fore.GREEN + Style.BRIGHT}5. {Fore.CYAN}Back to Main Menu{Style.RESET_ALL}")
            try:
                choice = int(input(f"{Fore.YELLOW + Style.BRIGHT}Select option [1-5]: {Style.RESET_ALL}").strip())
                if choice == 1:
                    self.display_accounts()
                    input(f"{Fore.YELLOW + Style.BRIGHT}Press Enter to continue...{Style.RESET_ALL}")
                elif choice == 2:
                    self.add_account()
                    input(f"{Fore.YELLOW + Style.BRIGHT}Press Enter to continue...{Style.RESET_ALL}")
                elif choice == 3:
                    self.edit_account()
                    input(f"{Fore.YELLOW + Style.BRIGHT}Press Enter to continue...{Style.RESET_ALL}")
                elif choice == 4:
                    self.delete_account()
                    input(f"{Fore.YELLOW + Style.BRIGHT}Press Enter to continue...{Style.RESET_ALL}")
                elif choice == 5:
                    break
                else:
                    self.log(f"{Fore.RED}✗ Invalid option. Choose 1-5{Style.RESET_ALL}")
                    input(f"{Fore.YELLOW + Style.BRIGHT}Press Enter to continue...{Style.RESET_ALL}")
            except ValueError:
                self.log(f"{Fore.RED}✗ Invalid input. Enter a number{Style.RESET_ALL}")
                input(f"{Fore.YELLOW + Style.BRIGHT}Press Enter to continue...{Style.RESET_ALL}")

    async def user_data(self, app_id: str, email: str, token: str, proxy=None, retries=5):
        url = f"{self.BASE_API}/api/atom/v1/userreferral/getpoint?appid={app_id}"
        headers = {
            **self.headers,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        for attempt in range(retries):
            try:
                proxies = proxy.as_proxies_dict if proxy else None
                response = requests.get(url=url, headers=headers, proxies=proxies, timeout=120)
                response.raise_for_status()
                result = response.json()
                return result["data"]
            except (ProxyError, SSLError) as e:
                if attempt < retries - 1:
                    self.print_message(email, proxy, Fore.YELLOW, f"✗ Proxy error, retrying: {str(e)}")
                    await asyncio.sleep(5)
                    continue
                proxy = self.rotate_proxy_for_account(email) if proxy else None
                self.print_message(email, proxy, Fore.YELLOW, f"✗ Failed to get data: {str(e)}")
                return None
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    continue
                self.print_message(email, proxy, Fore.YELLOW, f"✗ Failed to get data: {str(e)}")
                return None

    async def send_keepalive(self, app_id: str, email: str, token: str, use_proxy: bool, proxy=None, retries=5):
        url = f"{self.BASE_API}/chromeapi/dawn/v1/userreward/keepalive?appid={app_id}"
        data = json.dumps({"username": email, "extensionid": "fpdkjdnhkakefebpekbdhillbhonfjjp", "numberoftabs": 0, "_v": "1.1.6"})
        headers = {
            **self.headers,
            "Authorization": f"Bearer {token}",
            "Content-Length": str(len(data)),
            "Content-Type": "application/json",
        }
        for attempt in range(retries):
            try:
                proxies = proxy.as_proxies_dict if proxy else None
                response = requests.post(url=url, headers=headers, data=data, proxies=proxies, timeout=120)
                response.raise_for_status()
                result = response.json()
                return result["data"]
            except (ProxyError, SSLError) as e:
                if attempt < retries - 1:
                    self.print_message(email, proxy, Fore.YELLOW, f"✗ Proxy error, retrying: {str(e)}")
                    await asyncio.sleep(5)
                    continue
                proxy = self.rotate_proxy_for_account(email) if use_proxy else None
                self.print_message(email, proxy, Fore.RED, f"✗ Ping failed: {str(e)}")
                return None
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    continue
                self.print_message(email, proxy, Fore.RED, f"✗ Ping failed: {str(e)}")
                proxy = self.rotate_proxy_for_account(email) if use_proxy else None
                return None

    async def process_user_earning(self, app_id: str, email: str, token: str, use_proxy: bool):
        while True:
            proxy = self.get_next_proxy_for_account(email) if use_proxy else None
            user = await self.user_data(app_id, email, token, proxy)
            if user:
                referral_point = user.get("referralPoint", {}).get("commission", 0)
                reward_point = user.get("rewardPoint", {})
                reward_points = sum(
                    value for key, value in reward_point.items()
                    if "points" in key.lower() and isinstance(value, (int, float))
                )
                total_points = referral_point + reward_points
                self.print_message(email, proxy, Fore.GREEN, f"✓ Earning: {total_points:.0f} PTS")
            await asyncio.sleep(10 * 60)

    async def process_send_keepalive(self, app_id: str, email: str, token: str, use_proxy: bool):
        while True:
            proxy = self.get_next_proxy_for_account(email) if use_proxy else None
            print(
                f"{Fore.CYAN + Style.BRIGHT}╭─[{datetime.now().astimezone(wib).strftime('%x %X %Z')}]{Style.RESET_ALL}\n"
                f"{Fore.CYAN + Style.BRIGHT}╰──▶{Style.RESET_ALL} {Fore.BLUE + Style.BRIGHT}Sending ping...{Style.RESET_ALL}",
                end="\r",
                flush=True
            )
            keepalive = await self.send_keepalive(app_id, email, token, use_proxy, proxy)
            if keepalive and keepalive.get("success"):
                server_name = keepalive.get("servername", "N/A")
                self.print_message(email, proxy, Fore.GREEN, f"✓ Ping successful | Server: {server_name}")
            print(
                f"{Fore.CYAN + Style.BRIGHT}╭─[{datetime.now().astimezone(wib).strftime('%x %X %Z')}]{Style.RESET_ALL}\n"
                f"{Fore.CYAN + Style.BRIGHT}╰──▶{Style.RESET_ALL} {Fore.BLUE + Style.BRIGHT}Waiting 10 minutes for next ping...{Style.RESET_ALL}",
                end="\r",
                flush=True
            )
            await asyncio.sleep(10 * 60)

    async def process_accounts(self, app_id: str, email: str, token: str, use_proxy: bool):
        tasks = [
            asyncio.create_task(self.process_user_earning(app_id, email, token, use_proxy)),
            asyncio.create_task(self.process_send_keepalive(app_id, email, token, use_proxy))
        ]
        await asyncio.gather(*tasks)

    async def farming(self):
        try:
            accounts = self.load_accounts()
            if not accounts:
                self.log(f"{Fore.RED + Style.BRIGHT}✗ No accounts loaded{Style.RESET_ALL}")
                input(f"{Fore.YELLOW + Style.BRIGHT}Press Enter to return to menu...{Style.RESET_ALL}")
                return
            use_proxy_choice = self.print_question()
            use_proxy = False
            if use_proxy_choice in [1, 2]:
                use_proxy = True
            self.clear_terminal()
            self.welcome()
            self.log(
                f"{Fore.GREEN + Style.BRIGHT}✓ Accounts loaded: {Style.RESET_ALL}"
                f"{Fore.WHITE + Style.BRIGHT}{len(accounts)}{Style.RESET_ALL}"
            )
            if use_proxy:
                await self.load_proxies(use_proxy_choice)
            self.log(f"{Fore.CYAN + Style.BRIGHT}━{Style.RESET_ALL}"*50)
            tasks = []
            for account in accounts:
                app_id = self.generate_app_id()
                email = account.get('Email')
                token = account.get('Token')
                if app_id and "@" in email and token:
                    tasks.append(asyncio.create_task(self.process_accounts(app_id, email, token, use_proxy)))
            await asyncio.gather(*tasks)
        except Exception as e:
            self.log(f"{Fore.RED+Style.BRIGHT}✗ Error: {e}{Style.RESET_ALL}")
            input(f"{Fore.YELLOW + Style.BRIGHT}Press Enter to return to menu...{Style.RESET_ALL}")

    def main_menu(self):
        while True:
            self.clear_terminal()
            self.welcome()
            self.log(f"{Fore.YELLOW + Style.BRIGHT}Main Menu:{Style.RESET_ALL}")
            print(f"{Fore.GREEN + Style.BRIGHT}1. {Fore.CYAN}Start Farming{Style.RESET_ALL}")
            print(f"{Fore.GREEN + Style.BRIGHT}2. {Fore.CYAN}Manage Accounts{Style.RESET_ALL}")
            print(f"{Fore.GREEN + Style.BRIGHT}3. {Fore.CYAN}Exit{Style.RESET_ALL}")
            try:
                choice = int(input(f"{Fore.YELLOW + Style.BRIGHT}Select option [1-3]: {Style.RESET_ALL}").strip())
                if choice == 1:
                    asyncio.run(self.farming())
                elif choice == 2:
                    self.accounts_menu()
                elif choice == 3:
                    self.log(f"{Fore.RED + Style.BRIGHT}✗ Exiting bot{Style.RESET_ALL}")
                    break
                else:
                    self.log(f"{Fore.RED}✗ Invalid option. Choose 1-3{Style.RESET_ALL}")
                    input(f"{Fore.YELLOW + Style.BRIGHT}Press Enter to continue...{Style.RESET_ALL}")
            except ValueError:
                self.log(f"{Fore.RED}✗ Invalid input. Enter a number{Style.RESET_ALL}")
                input(f"{Fore.YELLOW + Style.BRIGHT}Press Enter to continue...{Style.RESET_ALL}")

if __name__ == "__main__":
    try:
        bot = Dawn()
        bot.main_menu()
    except KeyboardInterrupt:
        print(
            f"{Fore.CYAN + Style.BRIGHT}╭─[{datetime.now().astimezone(wib).strftime('%x %X %Z')}]{Style.RESET_ALL}\n"
            f"{Fore.CYAN + Style.BRIGHT}╰──▶{Style.RESET_ALL} {Fore.RED + Style.BRIGHT}✗ Bot stopped by user{Style.RESET_ALL}"
        )
