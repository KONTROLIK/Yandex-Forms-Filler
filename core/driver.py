from __future__ import annotations

import ctypes
import glob
import os
import shutil
import tempfile
import time
from typing import Callable

from selenium import webdriver
from selenium.common.exceptions import SessionNotCreatedException, TimeoutException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

Log = Callable[[str], None]


def _noop(message: str) -> None:
    pass


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def find_cached_driver(browser: str) -> str | None:
    if browser == "chrome":
        pattern = os.path.expanduser(
            r"~\.cache\selenium\chromedriver\win64\*\chromedriver.exe"
        )
    else:
        pattern = os.path.expanduser(
            r"~\.cache\selenium\msedgedriver\win64\*\msedgedriver.exe"
        )
    found = sorted(glob.glob(pattern))
    return found[-1] if found else None


def _base_args(profile: str) -> list[str]:
    return [
        "--window-size=1400,2400",
        "--lang=ru-RU",
        "--no-first-run",
        "--disable-extensions",
        "--disable-blink-features=AutomationControlled",
        f"--user-data-dir={profile}",
    ]


def _build_edge_options(profile: str, headless: bool, fallback: bool) -> EdgeOptions:
    opts = EdgeOptions()
    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
    for arg in _base_args(profile):
        opts.add_argument(arg)
    opts.page_load_strategy = "eager"
    if fallback:
        opts.add_argument("--no-sandbox")
    opts.add_experimental_option(
        "excludeSwitches", ["enable-automation", "enable-logging"]
    )
    opts.add_experimental_option("useAutomationExtension", False)
    return opts


def _build_chrome_options(profile: str, headless: bool, fallback: bool) -> ChromeOptions:
    opts = ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
    for arg in _base_args(profile):
        opts.add_argument(arg)
    opts.page_load_strategy = "eager"
    if fallback:
        opts.add_argument("--no-sandbox")
    opts.add_experimental_option(
        "excludeSwitches", ["enable-automation", "enable-logging"]
    )
    opts.add_experimental_option("useAutomationExtension", False)
    return opts


def make_driver(
    browser: str = "edge",
    headless: bool = True,
    log: Log = _noop,
    log_dir: str | None = None,
) -> tuple[webdriver.Remote, str]:
    browser = (browser or "edge").lower()
    if headless and is_admin():
        log(
            "Внимание: приложение запущено от администратора. "
            "Edge/Chrome в headless-режиме может не стартовать."
        )

    driver_path = find_cached_driver(browser)
    if driver_path:
        log(f"Драйвер: {driver_path}")
    else:
        log("Драйвер не найден в кэше, используется Selenium Manager")

    last_error: Exception | None = None
    for attempt in range(1, 4):
        profile = tempfile.mkdtemp(prefix=f"yaform-{browser}-")
        log_path = None
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, f"driver_{os.getpid()}_{attempt}.log")
        try:
            if browser == "chrome":
                options = _build_chrome_options(profile, headless, attempt > 1)
                service = (
                    ChromeService(executable_path=driver_path, log_output=log_path)
                    if driver_path
                    else ChromeService(log_output=log_path)
                )
                driver = webdriver.Chrome(options=options, service=service)
            else:
                options = _build_edge_options(profile, headless, attempt > 1)
                service = (
                    EdgeService(executable_path=driver_path, log_output=log_path)
                    if driver_path
                    else EdgeService(log_output=log_path)
                )
                driver = webdriver.Edge(options=options, service=service)
            driver.set_page_load_timeout(60)
            driver.implicitly_wait(0)
            return driver, profile
        except SessionNotCreatedException as exc:
            last_error = exc
            shutil.rmtree(profile, ignore_errors=True)
            log(f"Не удалось запустить браузер (попытка {attempt}/3): {exc.msg}")
            if log_path:
                log(f"Лог драйвера: {log_path}")
            if attempt < 3:
                time.sleep(6)
        except Exception:
            shutil.rmtree(profile, ignore_errors=True)
            raise
    assert last_error is not None
    raise last_error


def open_url(
    driver: webdriver.Remote,
    url: str,
    log: Log = _noop,
    timeout: int = 45,
    attempts: int = 3,
) -> None:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            driver.get(url)
        except TimeoutException as exc:
            last_error = exc
            log(f"Таймаут загрузки страницы (попытка {attempt}/{attempts})")
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.QuestionMarkup.Question, form")
                )
            )
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script("return document.readyState")
                in ("interactive", "complete")
            )
            return
        except TimeoutException as exc:
            last_error = exc
            log(
                "Форма не появилась (попытка "
                f"{attempt}/{attempts}), url={driver.current_url}"
            )
            if attempt < attempts:
                time.sleep(10)
    if last_error is not None:
        raise last_error
    raise TimeoutException("Форма не загрузилась")


def quit_driver(driver: webdriver.Remote | None, profile: str | None) -> None:
    if driver is not None:
        try:
            driver.quit()
        except Exception:
            pass
    if profile:
        shutil.rmtree(profile, ignore_errors=True)
