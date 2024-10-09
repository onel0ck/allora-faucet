# Allora Faucet

This project automates the process of requesting tokens from the Allora testnet faucet for multiple addresses.

**Disclaimer:** This project is for educational purposes only. Use it responsibly and in accordance with Allora's terms of service.

https://x.com/1l0ck

## Features

- Multi-processed faucet requests for efficient processing
- Proxy support for enhanced privacy
- Automated reCAPTCHA solving using CapMonster
- Dynamic progress bar with real-time status updates
- Detailed logging with color-coded output
- Results saved to separate files for successful and failed requests

## Setup

1. Clone the repository:
   ```
   git clone https://github.com/onel0ck/allora-faucet.git
   cd allora-faucet
   ```

2. Create a virtual environment and activate it:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

4. Prepare the data files:
   - `proxies.txt`: Contains proxy addresses in the format `http://login:password@ip:port`
   - `addresses.txt`: Contains Allora addresses to request tokens for, one per line

5. Set up your CapMonster API key:
   - Open `main.py` and replace `YOUR_API` in the `CAPMONSTER_API_KEY` variable with your actual CapMonster API key.

## Usage

Run the script:
```
python main.py
```

## Results

- Successful requests will be saved in `results/SUCCESS.txt`
- Failed requests will be saved in `results/FAIL.txt`
- Detailed logs will be saved in `results/log.txt`
- Console output will show real-time progress and final results

## Configuration

You can modify the following parameters in the `main.py` file:
- `MAX_PROCESSES`: Maximum number of concurrent processes
- `CAPTCHA_TIMEOUT`: Timeout for CAPTCHA solving
- `FAUCET_URL`: URL of the Allora testnet faucet
