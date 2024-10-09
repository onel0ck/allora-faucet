import requests
import random
import json
import time
import os
from loguru import logger
from capmonster_python import RecaptchaV2Task
from multiprocessing import Pool, cpu_count, Manager
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn

# Configuration
FAUCET_URL = "https://faucet.testnet-1.testnet.allora.network"
CAPMONSTER_API_KEY = "YOUR_API"
RECAPTCHA_SITE_KEY = "6LeWDBYqAAAAAIcTRXi4JLbAlu7mxlIdpHEZilyo"
CAPTCHA_TIMEOUT = 120
MAX_PROCESSES = min(cpu_count(), 5)  # Use no more than 5 processes or CPU core count
RESULTS_DIR = "results"

os.makedirs(RESULTS_DIR, exist_ok=True)

logger.remove()
logger.add(os.path.join(RESULTS_DIR, "log.txt"), format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")

console = Console()

def load_file(filename):
    with open(filename, 'r') as file:
        return [line.strip() for line in file]

def solve_recaptcha(url):
    capmonster = RecaptchaV2Task(CAPMONSTER_API_KEY)
    task_id = capmonster.create_task(url, RECAPTCHA_SITE_KEY)
    
    start_time = time.time()
    while time.time() - start_time < CAPTCHA_TIMEOUT:
        result = capmonster.join_task_result(task_id, maximum_time=5)
        if result.get("gRecaptchaResponse"):
            return result.get("gRecaptchaResponse")
        time.sleep(5)
    
    raise Exception("Failed to solve reCAPTCHA within the time limit")

def send_faucet_request(address_proxy):
    address, proxy = address_proxy
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0"
    ]
    headers = {"User-Agent": random.choice(user_agents)}
    session = requests.Session()
    session.proxies = {"http": proxy, "https": proxy}

    try:
        logger.info(f"{address} START")
        
        response = session.get(f"{FAUCET_URL}/config.json", headers=headers)
        response.raise_for_status()

        logger.info(f"{address} START CAPTCHA")
        recaptcha_token = solve_recaptcha(FAUCET_URL)
        logger.info(f"{address} CAPTCHA SOLVED")

        payload = {
            "chain": "allora-testnet-1",
            "address": address,
            "recapcha_token": recaptcha_token
        }
        response = session.post(f"{FAUCET_URL}/send", json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        
        if result.get("code") == 0 or (result.get("code") == 1 and "Too many faucet requests" in result.get("message", "")):
            logger.info(f"SUCCESS {address}")
            return True, address
        else:
            logger.error(f"ERROR {address}: {result.get('message')}")
            return False, address

    except Exception as e:
        logger.error(f"ERROR {address}: {str(e)}")
        return False, address

def process_address(args):
    address_proxy, progress_queue = args
    max_retries = 3
    for attempt in range(max_retries):
        success, address = send_faucet_request(address_proxy)
        if success:
            progress_queue.put(1)
            return success, address
        time.sleep(5)
    progress_queue.put(1)
    return False, address_proxy[0]

def main():
    proxies = load_file("proxies.txt")
    addresses = load_file("addresses.txt")

    address_proxy_pairs = list(zip(addresses, proxies))

    progress = Progress(
        SpinnerColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        BarColumn(),
        TextColumn("[bold blue]{task.fields[status]}", justify="right"),
    )

    with Manager() as manager:
        progress_queue = manager.Queue()
        pool_args = [(pair, progress_queue) for pair in address_proxy_pairs]

        with Pool(MAX_PROCESSES) as pool:
            results = []
            task = progress.add_task("[green]Processing", total=len(address_proxy_pairs), status="Starting...")

            with Live(Panel(progress), refresh_per_second=10) as live:
                async_results = pool.map_async(process_address, pool_args)
                while not async_results.ready():
                    completed = 0
                    while not progress_queue.empty():
                        progress_queue.get()
                        completed += 1
                    progress.update(task, advance=completed, status=f"Processed {progress.tasks[0].completed}/{len(address_proxy_pairs)}")
                    time.sleep(0.1)
                results = async_results.get()

    console.print("\nResults:")
    with open(os.path.join(RESULTS_DIR, "SUCCESS.txt"), "w") as success_file, \
         open(os.path.join(RESULTS_DIR, "FAIL.txt"), "w") as fail_file:
        for success, address in results:
            if success:
                console.print(f"[green]SUCCESS:[/green] {address}")
                success_file.write(f"{address}\n")
            else:
                console.print(f"[red]ERROR:[/red] {address}")
                fail_file.write(f"{address}\n")

if __name__ == "__main__":
    main()