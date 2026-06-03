# Quick snippet using Selenium
from selenium import webdriver
from bs4 import BeautifulSoup

driver = webdriver.Chrome()
driver.get("www.linkedin.com/in/kalinaterzieva")

# LinkedIn often hides data until you scroll
driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

soup = BeautifulSoup(driver.page_source, 'html.parser')
name = soup.find('h1', {'class': 'text-heading-xlarge'}).get_text().strip()
print(f"Scraped: {name}")
