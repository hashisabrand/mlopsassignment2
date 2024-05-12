from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.operators.bash_operator import BashOperator
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def extract_article_details(url):
    import logging
import requests
from bs4 import BeautifulSoup

def extract_article_details(url):
    """
    Extracts title and description from a given URL using BeautifulSoup.
    Handles network errors and HTML parsing issues gracefully.
    """
    try:
        response = requests.get(url, timeout=10)  # Make an HTTP request to the URL
        response.raise_for_status()  # Raise an exception for HTTP errors
        soup = BeautifulSoup(response.text, 'html.parser')  # Parse the HTML content
        
        # Extract the title of the article
        title_element = soup.find('title')
        title = title_element.text.strip() if title_element else None
        
        # Extract all paragraph contents and combine into one description string
        paragraphs = soup.find_all('p')
        description = ' '.join([p.text.strip() for p in paragraphs if p.text.strip()]) if paragraphs else None
        
        # Log warnings for missing title or description
        if not title or not description:
            logging.warning(f"No valid title or description for URL: {url}")
            return None, None
        return title, description
    except requests.exceptions.RequestException as e:
        logging.error(f"Request failed for {url}: {str(e)}")
        return None, None
    except Exception as e:
        logging.error(f"Error processing {url}: {str(e)}")
        return None, None


def extract():
    """
    Extracts links, titles, and descriptions from the homepages of predefined news sources.
    Returns a list of dictionaries containing the extracted data.
    Limits the total number of articles to 50.
    """
    data = []
    sources = {
        'BBC': 'https://www.bbc.com',
        'Dawn': 'https://www.dawn.com'
    }
    selectors = {
        'BBC': 'a[data-testid="internal-link"]',
        'Dawn': 'article.story a.story__link'
    }

    article_counter = 0

    for source, base_url in sources.items():
        response = requests.get(base_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        links = [a['href'] for a in soup.select(selectors.get(source, '')) if 'href' in a.attrs]
        links = [link if link.startswith('http') else base_url + link for link in links]

        for link in links:
            title, description = extract_article_details(link)
            if title and description:
                data.append({'title': title, 'description': description, 'source': source})
                article_counter += 1
                if article_counter >= 7:
                    break

        if article_counter >= 7:
            break

    return data


def transform(data):
    """
    Transforms extracted data by cleaning and formatting text.
    Removes special characters and excessive whitespace.
    """
    transformed_data = []
    for i, row in enumerate(data):
        # Clean and format the title and description text
        title = re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', row['title'])).strip()
        description = re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', row['description'])).strip()
        transformed_data.append({
            'id': i + 1,
            'title': title,
            'description': description,
            'source': row['source']
        })
    return transformed_data


def load(data):
    """
    Loads the transformed data into a CSV file.
    Filters out any entries without a title or description before saving.
    """
    # Get the directory of the current DAG file
    dag_directory = os.path.dirname(__file__)

    # Specify the relative path to the CSV file
    csv_file_path = os.path.join(dag_directory, 'extracted_data.csv')

    df = pd.DataFrame(data)
    df = df.dropna(subset=['title', 'description'])  # Ensure data completeness
    df.to_csv(csv_file_path, index=False)



# Define the DAG configuration
dag = DAG(
    dag_id='web_article_scraping',
    start_date=datetime(2024, 5, 7),
    schedule_interval='@daily'
)

# Define tasks using PythonOperator and BashOperator
extract_task = PythonOperator(
    task_id='extract',
    python_callable=extract,
    dag=dag
)

transform_task = PythonOperator(
    task_id='transform',
    python_callable=lambda: transform(extract()),
    dag=dag
)

load_task = PythonOperator(
    task_id='load',
    python_callable=lambda: load(transform(extract())),
    dag=dag
)
    
# Construct the DVC add and push command
dvc_add_and_push_command = f"""
cd {os.path.dirname(__file__)}
pip install dvc && \
pip install dvc-gdrive && \
dvc init -f --no-scm && \
dvc remote add -d mygoogleDrive gdrive://1V2UrWUsSbvIBEZOPf39Cu3Cfqbnll4Gh && \
dvc add extracted_data.csv && \
dvc push -r mygoogleDrive
"""


# Define the BashOperator
dvc_task = BashOperator(
    task_id='dvc_add_and_push',
    bash_command=dvc_add_and_push_command,
    dag=dag
)





# Set dependencies between tasks to ensure correct task execution order
extract_task >> transform_task >> load_task >> dvc_task