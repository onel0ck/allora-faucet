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
FAUCET_URLS = {
    "main": "https://faucet.testnet-1.testnet.allora.network",
    "secondary": "https://allora-faucet-api.iamscray.dev"
}
CAPMONSTER_API_KEY = "287d0febef238cf1fc3370732dc468b3"
RECAPTCHA_SITE_KEY = "6LeWDBYqAAAAAIcTRXi4JLbAlu7mxlIdpHEZilyo"
CAPTCHA_TIMEOUT = 120
MAX_PROCESSES = min(cpu_count(), 10)
RESULTS_DIR = "results"
MAX_RETRIES = 3
RETRY_DELAY = 5

os.makedirs(RESULTS_DIR, exist_ok=True)

logger.remove()
logger.add(os.path.join(RESULTS_DIR, "log.txt"), format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="DEBUG")

console = Console()

def load_file(filename):
    with open(filename, 'r') as file:
        return [line.strip() for line in file]

def solve_recaptcha(url, address):
    capmonster = RecaptchaV2Task(CAPMONSTER_API_KEY)
    
    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"{address} | Captcha attempt {attempt + 1}")
            task_id = capmonster.create_task(url, RECAPTCHA_SITE_KEY)
            logger.debug(f"{address} | Captcha task created: {task_id}")
            
            start_time = time.time()
            while time.time() - start_time < CAPTCHA_TIMEOUT:
                result = capmonster.join_task_result(task_id, maximum_time=10)
                if result.get("gRecaptchaResponse"):
                    logger.debug(f"{address} | Captcha solved successfully")
                    return result.get("gRecaptchaResponse")
                logger.debug(f"{address} | Waiting for captcha solution...")
                time.sleep(2)
            
            raise Exception("Captcha solving timed out")
        
        except Exception as e:
            logger.warning(f"{address} | Captcha solving attempt {attempt + 1} failed: {str(e)}")
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1)
                logger.info(f"{address} | Retrying captcha in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                logger.error(f"{address} | All captcha solving attempts failed")
                raise

def send_secondary_faucet_request(session, address, headers):
    payload = {"address": address}
    response = session.post(f"{FAUCET_URLS['secondary']}/claim", json=payload, headers=headers)
    response.raise_for_status()
    result = response.json()
    
    if result.get("code") == 0:
        return "SUCCESS", result.get("message")
    elif result.get("code") == 1:
        return "ALREADY_RECEIVED", result.get("message")
    return "ERROR", result.get("message")

def send_main_faucet_request(session, address, recaptcha_token, headers):
    payload = {
        "chain": "allora-testnet-1",
        "address": address,
        "recapcha_token": recaptcha_token
    }
    response = session.post(f"{FAUCET_URLS['main']}/send", json=payload, headers=headers)
    
    if response.status_code == 429:
        return "ALREADY_RECEIVED", "Too many requests"
    
    response.raise_for_status()
    result = response.json()
    
    if result.get("code") == 0:
        return "SUCCESS", result.get("message")
    elif result.get("code") == 1 and "Too many faucet requests" in result.get("message", ""):
        return "ALREADY_RECEIVED", result.get("message")
    return "ERROR", result.get("message")

def send_faucet_request(address_proxy_faucet):
    address, proxy, use_secondary = address_proxy_faucet
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0"
    ]
    headers = {
        "User-Agent": random.choice(user_agents),
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Origin": "https://allora-faucet.iamscray.dev",
        "Referer": "https://allora-faucet.iamscray.dev/"
    }
    
    session = requests.Session()
    session.proxies = {"http": proxy, "https": proxy}

    try:
        logger.info(f"{address} | START | Using {'secondary' if use_secondary else 'main'} faucet")
        
        if use_secondary:
            status, message = send_secondary_faucet_request(session, address, headers)
        else:
            response = session.get(f"{FAUCET_URLS['main']}/config.json", headers=headers)
            response.raise_for_status()
            logger.debug(f"{address} | Config fetched successfully")
            
            logger.info(f"{address} | START CAPTCHA")
            recaptcha_token = solve_recaptcha(FAUCET_URLS['main'], address)
            logger.info(f"{address} | CAPTCHA SOLVED")
            
            status, message = send_main_faucet_request(session, address, recaptcha_token, headers)
        
        logger.info(f"{status} {address}: {message}")
        return status, address

    except Exception as e:
        logger.error(f"ERROR {address}: {str(e)}")
        return "ERROR", address

def process_address(args):
    address_proxy_faucet, progress_queue = args
    max_retries = 3
    for attempt in range(max_retries):
        logger.debug(f"{address_proxy_faucet[0]} | Processing attempt {attempt + 1}")
        status, address = send_faucet_request(address_proxy_faucet)
        if status in ["SUCCESS", "ALREADY_RECEIVED"]:
            progress_queue.put(1)
            return status, address
        else:
            logger.info(f"{address} | Error occurred, retrying in 5 seconds")
            time.sleep(5)
    progress_queue.put(1)
    return status, address_proxy_faucet[0]

def main(use_secondary=False):
    proxies = load_file("proxies.txt")
    addresses = load_file("addresses.txt")

    logger.info(f"Loaded {len(addresses)} addresses and {len(proxies)} proxies")
    logger.info(f"Using {'secondary' if use_secondary else 'main'} faucet")

    address_proxy_pairs = [(addr, proxy, use_secondary) for addr, proxy in zip(addresses, proxies)]

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

    logger.info("Processing completed. Writing results to files.")

    console.print("\nResults:")
    with open(os.path.join(RESULTS_DIR, "SUCCESS.txt"), "w") as success_file, \
         open(os.path.join(RESULTS_DIR, "ALREADY_RECEIVED.txt"), "w") as already_received_file, \
         open(os.path.join(RESULTS_DIR, "FAIL.txt"), "w") as fail_file:
        for status, address in results:
            if status == "SUCCESS":
                console.print(f"[green]SUCCESS:[/green] {address}")
                success_file.write(f"{address}\n")
            elif status == "ALREADY_RECEIVED":
                console.print(f"[yellow]ALREADY RECEIVED:[/yellow] {address}")
                already_received_file.write(f"{address}\n")
            else:
                console.print(f"[red]ERROR:[/red] {address}")
                fail_file.write(f"{address}\n")

    logger.info("Results have been written to files in the results directory.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--secondary", action="store_true", help="Use secondary faucet")
    args = parser.parse_args()
    main(use_secondary=args.secondary)
