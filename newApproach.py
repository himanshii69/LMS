from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain.chat_models import ChatOpenAI
from flask import Flask, jsonify, request, abort
from flask_cors import CORS
from flask import json
from bs4 import BeautifulSoup
from oauth2client.service_account import ServiceAccountCredentials
import traceback
import requests
import random
import gspread
import pandas as pd
import json

app = Flask(__name__)
cors = CORS(app, allow_headers=["Content-Type","Authorization", "X-Requested-With"])

llm = ChatOpenAI(openai_api_key="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",model_name='gpt-3.5-turbo', temperature=0.1)

def convert_and_access(text):
    key_value_pairs = text.split("\n")
    data = {}
    for pair in key_value_pairs:
        key, value = pair.split(":", 1)
        key = key.strip()
        value = value.strip()
        data[key] = value

    # Convert the dictionary to JSON
    json_data = json.dumps(data)

    # Load the JSON string into a Python dictionary
    output_dict = json.loads(json_data)
    category = output_dict.get("Category")
    domain = output_dict.get("Domain")
    return category, domain

def splitting(text):
    lines = text.split('\n')
    key_value_pairs = {}

    for line in lines:
        parts = line.split(':')
        key = parts[0].strip()
        value = parts[1].strip()
        if key in key_value_pairs:
            key_value_pairs[key].append(value)
        else:
            key_value_pairs[key] = [value]
    return key_value_pairs

def get_domain(description):
    sheet_url = "https://docs.google.com/spreadsheets/d/1X-Uyfd8gQKHJlaYdbvhvuMYEzna8rK951ogtZV7wxVM/edit#gid=0"
    worksheet = openSheet(sheet_url)

    # Extract data as a list of lists
    data = worksheet.get_all_values()

    # Convert the data to a DataFrame
    df = pd.DataFrame(data[1:], columns=data[0])

    # Get unique values from the "Domain" column
    unique_domains = df['Domain'].unique()
    print(unique_domains)
    
    pdf_temp = """

                    I want you to act as a BDE Manager. I will provide you a job description and a list of domains. Your task is to analyse the given job description and provide the best matching domains from the provided list of domains.  

                    if exact domain is not present in the list, then prefer returning best closest domain for the job description from the provided list.  

                    The output should be only one of the names from the provided list. 

                    ***Content***:
                    Content: '{content}'

                    ***Job Description***:
                    Job Description: '{job_description}'

                    ***Output Format***:
                                domain name

                    Strict Rules:
                    1. only return domain name in the output from the content and do not return anything else on your own.
                     
                    

                    """

    pdf_prompt=PromptTemplate(input_variables=['content','job_description'],
                                template=pdf_temp)

    chain=LLMChain(llm=llm,prompt=pdf_prompt)
    chat=chain({'content':unique_domains,'job_description':description})
    print(chat['text'])
    return chat.get("text", "")
       
def check_ratings(domain):
    # Open the Google Sheet by URL
    sheet_url = "https://docs.google.com/spreadsheets/d/1X-Uyfd8gQKHJlaYdbvhvuMYEzna8rK951ogtZV7wxVM/edit#gid=0"
    worksheet = openSheet(sheet_url)

    # Extract data as a list of dictionaries
    data = worksheet.get_all_records(expected_headers=["Domain", "Google Rating ", "Apple Rating "])

    # Convert the data to a DataFrame
    df = pd.DataFrame(data)

    # Convert 'Google Rating' and 'Apple Rating' columns to numeric
    df['Google Rating '] = pd.to_numeric(df['Google Rating '], errors='coerce')
    df['Apple Rating '] = pd.to_numeric(df['Apple Rating '], errors='coerce')

    # Define rating threshold
    rating_threshold = 3.5

    # Filter the DataFrame based on the domain and rating threshold
    filtered_df = df[(df['Domain'] == domain) & ((df['Google Rating '] > rating_threshold) | (df['Apple Rating '] > rating_threshold))]

    # Get the index values of the filtered rows
    result = filtered_df.index.tolist()
    print(result)
    return result

def get_description(ratings_index, job_description):
    sheet_url = "https://docs.google.com/spreadsheets/d/1X-Uyfd8gQKHJlaYdbvhvuMYEzna8rK951ogtZV7wxVM/edit#gid=0"
    worksheet = openSheet(sheet_url)
    data = worksheet.get_all_records(expected_headers=["App Description "])

    dict_of_descriptions = {}
    
    for index in ratings_index:
        # Check if the index is within the range of data rows
        if 0 < index <= len(data):
            # Get the description from the row corresponding to the index
            description = data[index]["App Description "].strip()

            if description != '':
                dict_of_descriptions[index] = description
        else:
            dict_of_descriptions[index] = None

    print(dict_of_descriptions)
    if len(dict_of_descriptions) >= 3:
        template = '''
            I want you to act as a Senior BDE Manager. I will provide you a job description and a dictionary of descriptions. Your task is to carefully analyze the job description. Now pick three descriptions from the dictionary that you can use as an example for the provided job description.  

            Find the best match that can be best suitable as an example for the provided job description, If best match is not found then prefer closest match that can be used as an example for the provided job description. 
            
            return corresponding index number of those matches.

            Job Description: 
            {job_description}

            Dictionary:
            {dictionary}

            Output Format:
                Index 1 
                Index 2
                Index 3
                
            Strict Rule : 
            Follow the format of output.
            The output should be in JSON.

'''
        prompt = PromptTemplate(input_variables=['job_description', 'dictionary'],
                                template=template)
        chain = LLMChain(llm=llm, prompt=prompt)
        chat = chain({'job_description': job_description, 'dictionary': dict_of_descriptions})
        print(chat)
        result = json.loads(chat.get("text", "{}").replace("```json", "").replace("```", ""))

        if len(result)<3 :
            while len(result) < 3:
                index_number = f'Index {len(result) + 1}'
                value = random.choice(ratings_index)
                result[index_number] = value

        index_numbers = list(result.values())
        
        sheet_url = "https://docs.google.com/spreadsheets/d/1X-Uyfd8gQKHJlaYdbvhvuMYEzna8rK951ogtZV7wxVM/edit#gid=0"
        worksheet = openSheet(sheet_url)

        data = worksheet.get_all_records(expected_headers=["App Description ","Google Play Store Link ", "Apple Store Link ", "Website ", ""]) 
        df = pd.DataFrame(data)
        data_dict = {}
        if index_numbers :
            for i in index_numbers:
                # Get the data corresponding to the index number
                # index_num = int(i)

                data = df.iloc[i]
                print(data)
                index_data = {
                'App Name': data['App Name '],
                'Google Link': data['Google Play Store Link '],
                'Apple Link': data['Apple Store Link '],
                'Description' : data['App Description '],
                'Website' : data['Website ']
                }
                data_dict[i] = index_data

        print(data_dict)
        return data_dict

    else:
        index_numbers = random.sample(ratings_index, 3)
        print(index_numbers)
        sheet_url = "https://docs.google.com/spreadsheets/d/1X-Uyfd8gQKHJlaYdbvhvuMYEzna8rK951ogtZV7wxVM/edit#gid=0"
        worksheet = openSheet(sheet_url)

        data = worksheet.get_all_records(expected_headers=["App Description ","Google Play Store Link ", "Apple Store Link ", "Website ", ""]) 
        df = pd.DataFrame(data)
        data_dict = {}
        if index_numbers :
            for i in index_numbers:
                # Get the data corresponding to the index number
                # index_num = int(i)

                data = df.iloc[i]
                print(data)
                index_data = {
                'App Name': data['App Name '],
                'Google Link': data['Google Play Store Link '],
                'Apple Link': data['Apple Store Link '],
                'Description' : data['App Description '],
                'Website' : data['Website ']
                }
                data_dict[i] = index_data

        print(data_dict)
        return data_dict

def get_category(description):

    list_of_category = ['AI Apps & Integration', 'Blockchain, NFT & Cryptocurrency', 'Desktop Application Development', 'Ecommerce Development', 'Game Design & Development',
                        'mobile development', 'Other - Software Development', 'Product Management & Scrum', 'QA Testing', 'Web & Mobile Design', 'web development']
    pdf_temp = """
                    As a Job Description Matching Specialist AI, Your task involves reviewing the job description to determine if the job description comes under any category provided to you. Your goal is to select the most suitable category that closely match the job requirements. If no matches are found, indicate an empty result.
 
                    please take your time to thoroughly analyse the job description and the content and do not rush to conclusions. 
 
                    ***Content***:
                    Content: '{content}
 
                    ***Job Description***:
                    Job Description: '{job_description}'
 
                    *Strict Rule* :Please only return one category that best suits the job description from the provided list and avoid returning any other information.
                    ***Output format***:
                                category: category
 
                    """
    pdf_prompt = PromptTemplate(input_variables=['job_description'],
                                template=pdf_temp)

    chain = LLMChain(llm=llm, prompt=pdf_prompt)
    chat = chain({'content': list_of_category, 'job_description': description})
    plain_text = chat['text']
    key, value = plain_text.split(':')
    key = key.strip()
    value = value.strip()
    key_value_pair = {key: value}
    print(key_value_pair['category'])
    return (key_value_pair['category'])

def openSheet(sheet_url):
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/drive"]

    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        "inlaid-fire-402909-427e2300473c.json", scope)

    # Authenticate with the Google Sheets API
    client = gspread.authorize(credentials)

    # Open the Google Sheet by URL
    sheet = client.open_by_url(sheet_url)

    # Get the first (and presumably only) worksheet
    worksheet = sheet.get_worksheet(0)
    return worksheet

def get_requirement(description):
    sheet_url = "https://docs.google.com/spreadsheets/d/1BSnuBcrHfGoNm5SB02vl7vUsil3L3Fcidbk6L8bfTIM/edit?pli=1#gid=0"

    worksheet = openSheet(sheet_url)
    data = worksheet.get_all_records(
        expected_headers=["Domain Name", "Category Name"])

    # Convert the data to a DataFrame
    df = pd.DataFrame(data)

    domain_names = df["Domain Name"].tolist()

    df_cleaned = df.dropna(subset=["Category Name"])
    categories_names = df_cleaned["Category Name"].tolist()

    data_dict = {}

    data_dict["domain"] = domain_names
    data_dict["category"] = categories_names

    pdf_temp = """
                As a Job Description Matching Specialist AI, your role is to meticulously align job descriptions with provided content. Your primary focus is on accurately identifying the requirements outlined in the job description and finding the best matches from the given content.
 
                Your task involves reviewing the job description and provided content to determine in which category and domain name, job description falls in. Your goal is to select the most suitable category and domain name from content that closely match the job requirements. If no matches are found, indicate an empty result.
 
 
                If technology name is in the job description and the same technology is present in the content provided to you, then it is the domain name.
 
                Please follow the guidelines below for optimal performance:
 
                1. Content Format: The content provided is a python dictionary containing key-value pairs. Ensure that you can effectively process the provided content format.
 
                Take your time to thoroughly analyse the overall requirements mentioned in the job description with the content and do not rush to conclusions. 
 
                ***Content***:
                Content: '{content}'
 
                ***Job Description***:
                Job Description: '{job_description}'
 
                **Strict Rule** :Please only return the matches that is best suitable with job description and avoid returning any other information. Return exact name of category and domain name from content provided to you, avoid returning name according to you. 
 
 
                ***Output format***: 
                                    Category : category name 
                                    Domain : domain name 
 
                """

    pdf_prompt = PromptTemplate(input_variables=['content', 'job_description'],
                                template=pdf_temp)

    chain = LLMChain(llm=llm, prompt=pdf_prompt)
    chat = chain({'content': data_dict, 'job_description': description})
    result = (chat['text'])
    category, domain = convert_and_access(result)
    return category, domain

def get_technology(description):
    pdf_temp = """
                As a AI model, your role is to accurately identifying the technical skills outlined in the job description. Please extract only the technical skills mentioned in the job description. Do not include soft skills or other terms.
 
                If no technical skills are mentioned in the job description, indicate an empty result.
 
                Ensure that the extracted technical skills include specific technologies, frameworks, languages, or tools relevant to the job role. Examples of technical skills may include "Python", "Java", "SQL", "AWS", "React.js", "Node.js", "HTML", "CSS", "JavaScript" and many more.
                Make sure if framework is used, then only return framework name, do not include technologiess used in it. 
 
                Example: If job description is - We are looking for some ongoing front- and back-end development for a web application built in Laravel with a MySQL database and Tailwind as the CSS framework.\n\nMain tasks evolve around:\n\n- Setting up routes, Blade files, Blade components for new landing pages including the front-end design of these pages with SEO friendly and Core Web Vitals performant HTML, JS and (Tailwind) CSS.\n- Editing, optimising Blade based designs of existing pages and components.\n- Expanding form validation in existing sign-up and checkout flows.\n- Moving transactional emails from Laravel to Drip via the Drip Order Activity API.\n- Expanding existing integration with Drip, mainly adding some tags based on certain webhooks / events.\n- Laravel web-app bug fixing and improvements / feature development; eg refer-a-friend tracking, self-service order renewal with payment.\n- Expanding GA4 tracking for micro- and macro-conversions, checkout flow steps etc.\n- Expanding Sentry event / error tracking.\n- Setting up / expanding some Admin GUI dashboard-like interfaces for monitoring orders.\n- CAPTCHA on contact form.\n\nThe first couple of months we would like to make good progress on these topics so availability is important in this phase. Later it will transition towards ad hoc development and support. Depending on the success of this web-app, there may be some bigger topics around version control & development environments, Laravel updates, CMS, translations, expanding the product offering, payment options etc.
                Then output should be laravel only. Do not include php, html, css or such technologies involved.
 
                ***Job Description***:
                Job Description: '{job_description}'
 
                **Strict Rule** : Please gain the understanding from the example provided to you and give output accordingly.
 
 
                ***Output format***: 
                                    Skills : skills
 
                """

    pdf_prompt = PromptTemplate(input_variables=['job_description'],
                                template=pdf_temp)

    chain = LLMChain(llm=llm, prompt=pdf_prompt)
    chat = chain({'job_description': description})
    result = (chat['text'])
    print("debugging statement:", result)
    try:
        key, value = result.split(": ", 1)
        if key.strip() == "Skills":
            if value.strip():  # If there's something after "Skills: "
                skills = [skill.strip() for skill in value.split(",")]
                if len(skills) == 1:
                    return skills[0]  # Return the single skill as a string
                else:
                    return skills  # Return multiple skills as a list
            else:
                return ""  # Return an empty list for empty skills
        else:
            return ""
    except ValueError:
        return ""


def filter_final_result(result, fetched_data):
    final_result = []
    for obj in result:
        for data in fetched_data:
            if data.get("Domain Name", "") == obj["Domain"]:
                if data[obj["Key"]].replace("\n", "").replace(" ", "") != "":
                    final_result.append(obj)
    return final_result


def get_domain_from_result(result, fetched_data, domain):
    filtered_result = []
    unmatched_results = []
    for obj in result:
        if obj.get("Domain", "").lower() == domain.lower():
            for data in fetched_data:
                if data.get("Domain Name", "").lower() == domain.lower():
                    num = obj["Key"].split(" ")[-1]
                    filtered_result.append(data[f"Website {num}"])
        else:
            unmatched_results.append(obj)
    if len(filtered_result) >= 3:
        return filtered_result[0:2]

    for obj in unmatched_results:
        for data in fetched_data:
            if data.get("Domain Name", "").lower() == obj.get("Domain", "").lower():
                num = obj["Key"].split(" ")[-1]
                filtered_result.append(data[f"Website {num}"])
            if len(filtered_result) == 3:
                return filtered_result

    return filtered_result


def get_data_columns(data, expected_headers):
    headers = data[0]
    indices = [headers.index(header) for header in expected_headers]
    fetched_data = [{header: row[index] for header, index in zip(
        expected_headers, indices)} for row in data[1:]]
    file_path = 'fetched_data.json'

# Write fetched_data to the file in JSON format
    with open(file_path, 'w') as f:
        json.dump(fetched_data, f)

    print("Data saved to", file_path)
    return json.loads(json.dumps(fetched_data).replace("\n", ","))


def generate_description(url):
    pdf_temp = """
                    As an AI, your role is to generate a description of 30-50 words for given content.
 
                    Carefully determine the url of website and generate description acoordingly. 
 
                    ***Content***:
                    Content: '{content}'
 
                    ***Output format***:
                                url : Description
                                url : Description
                                url : Description
                    ***Note*** : generate output in the format of JSON.
                    """

    pdf_prompt = PromptTemplate(input_variables=['content'],
                                template=pdf_temp)

    chain = LLMChain(llm=llm, prompt=pdf_prompt)
    chat = chain({'content': url})
    result = (chat['text'])
    result = result.replace("```json", "").replace("`", "")
    result = json.loads(result)
    print(result)
    return result


def load_sheet_data():
    sheet_url = "https://docs.google.com/spreadsheets/d/1BSnuBcrHfGoNm5SB02vl7vUsil3L3Fcidbk6L8bfTIM/edit?pli=1#gid=0"
    worksheet = openSheet(sheet_url)

    # Extract data as a list of lists
    data = worksheet.get_all_values()

    return data

def get_domain_from_sheet():
    data = load_sheet_data()

    # Convert the data to a DataFrame
    df = pd.DataFrame(data[1:], columns=data[0])

    # Get unique values from the "Domain" column
    unique_domains = df['Domain Name'].unique()
    unique_domains = [domain.strip().replace("\n", "")
                      for domain in unique_domains]
    return unique_domains

def get_tech_from_heading(heading):
    template = '''
        I want you to act as a Full Stack Developer. I will provide you a job heading and you will have to analyse it and provide the primary technology that job requires. 

        Technologies can be -  React, HTML, CSS, JavaScript, Python, Node.js, vue.js, ruby on rails, wix, woocommerce, Laravel, PHP etc. 

        The input is going to be a job heading and output should be one term, suggesting the technology mentioned.

        For example - if in job heading client wants a wix developer, ignore the other things written just return wix.
        Rules:
        The answer should suggest about the technology that is to be used, it should not answer with the process name.
        The output should only suggest single word containing primary technology and should not contain multiple technologies.

        ***Strict Rule*** - 
                        if no technology is mentioned in the job heading, Do not make assumptions and do not give technology on your own. Just return "". 

        Job Heading: 
        {heading}
        '''
    
    prompt = PromptTemplate(input_variables=['heading'],
                            template=template)
    chain = LLMChain(llm=llm, prompt=prompt)
    chat = chain({'heading': heading})
    return chat.get("text", "")


def get_primary_essence(job_description):
    template = '''
I want you to act as a BDE Manager. I will provide you a job description and you will have to analyse it and provide the primary technology that job requires.
The input is going to be a job description and output should be one term, suggesting the actual job requirement.
For example if in job description client wants a figma designer, ignore the other technology written just return figma.
Rules:
If the answer does not suggest the best technology match, then return the most relevant.
The answer should suggest about the technology that is to be used, it should not answer with the process name.
The output should only suggest single word containing primary technology and should not contain multiple technologies.

Job Description: 
{description}
'''
    prompt = PromptTemplate(input_variables=['description'],
                            template=template)
    chain = LLMChain(llm=llm, prompt=prompt)
    chat = chain({'description': job_description})
    return chat.get("text", "")


def get_relevant_domain(job_description, sheet_domains):
    template = '''
I want you to act as a BDE Manager. I will provide you a job description and a list of domains. Your task is to analyse the given job description and provide the best matching domains from the provided list of domains. The output domain name should be one of the names from the given domain names.

Rules:
Output should only contain single domain name.
If none of the provided domain name matches, return empty string ""

Job Description: 
{description}

Domains:
{domains}

Output Format:
Domain name

Strict Rule:
Follow the format of output.  
'''
    prompt = PromptTemplate(input_variables=['description', "domains"],
                            template=template)
    chain = LLMChain(llm=llm, prompt=prompt)
    chat = chain({'description': job_description, "domains": sheet_domains})
    return chat.get("text", "")


def get_technologies(job_description):
    template = '''
I want you to act as a BDE Manager. I will provide you a job description. Your task is to analyse the given job description and provide a list of technical skills required.

Rules:
Output should be in JSON format with keys - framework, technologies, other, where framework should contain a list of framework described in job description, technologies should contain a list of programming languages described in job description, remaining should come under others and avoid returning any irrelevent information.
If none of the the technologies are mentioned return an empty JSON Array.

Example Job Description:
Job Description:\nWe are on the lookout for an exceptionally talented Figma Designer specializing in creating detailed and user-friendly wireframes for a new SAAS web application. The Designer needs to have experience working closely with developers through the whole process of design through to shipping.\n\nThey will be methodical and thorough in labelling components.\n\nThis project requires a deep understanding of UI/X principles to ensure a seamless and engaging user experience. The selected designer will focus solely on developing a comprehensive wireframe that clearly outlines the structure and functionality of our upcoming web application.\n\nThey will take our existing FigJam wireframes and Figma Template and repurpose the template into a high-fidelity version of our application with labelled components, ready for our developer to build in React.\n\nHere is the figjam wireframes: https://www.figma.com/file/KdGDRVC6X54hJOwon1cSh6/Kite.site-Wireframes?type=whiteboard&node-id=0%3A1&t=dXQIywLYk88L7Qpb-1\n\nHere is the Figma template that we are using as our style guide:\nhttps://www.figma.com/file/dsrTu2aGrGEQq8YP2JJFu8/Kite.site-Prototype-using-Mercury-Template?type=design&node-id=1%3A7&mode=design&t=ceqZIyCwDviWpDpK-1

Example Output:
["figma"]

Job Description:
{description}
'''
    prompt = PromptTemplate(input_variables=['description'],
                            template=template)
    chain = LLMChain(llm=llm, prompt=prompt)
    chat = chain({'description': job_description})
    return json.loads(chat.get("text", "{}").replace("```json", "").replace("```", ""))


def get_primary_websites(primary_technology, refined_data):
    matching_websites = []

    for entry in refined_data:
        for i in range(1, 6):  # Assuming there are 5 website columns
            website_key = f'Website {i}'
            technology_key = f'Website Technology {i}'
            
            if technology_key in entry and primary_technology.lower() in entry[technology_key].lower():
                matching_websites.append({
                    'Domain Name': entry['Domain Name'],
                    'Website': entry[website_key]
                })

    return matching_websites

def get_technology_websites(technologies, refined_data):
    template = '''

'''
    prompt = PromptTemplate(input_variables=['technologies', "refined_data"],
                            template=template)
    chain = LLMChain(llm=llm, prompt=prompt)
    chat = chain({'technologies': technologies,
                 "refined_data": refined_data})
    response = chat.get("text", "{}").replace("```json", "").replace("```", "")
    return json.loads(response)

def match_websites_from_data(primary_technology, technologies, domain):
    sheet_data = load_sheet_data()
    sheet_data = pd.DataFrame(sheet_data[1:], columns=sheet_data[0])
    refined_data = sheet_data[["Domain Name", "Website 1", "Website Technology 1", "Website 2", "Website Technology 2", "Website 3", "Website Technology 3", "Website 4", "Website Technology 4", "Website 5", "Website Technology 5"]]
    refined_data = refined_data.to_dict("records")
    websites = get_primary_websites(primary_technology, refined_data)
    final_result = []
    unmatched_result = []
    # matching with domain if the result website are from essance
    for website in websites:
        if website.get("Domain Name").lower().strip() == domain.lower().strip():
            final_result.append(website)
        else:
            unmatched_result.append(website)
    while len(final_result) < 3 and unmatched_result:
        final_result.append(unmatched_result.pop())
    print(websites)
    return final_result

@app.route('/fetch-examples', methods=['POST'])
def handle_request():
    try:
        data = request.get_json()
        description = data.get('job_description')
        heading = data.get('job_heading')

        Category = get_category(description)
        print("category", Category)
        if Category.lower() in ['ai apps & integration', 'blockchain, nft & cryptocurrency' , 'desktop application development' , 'ecommerce development' , 'game design & development' , 'other - software development' , 'product management & scrum' , 'qa testing' , 'web & mobile design' , 'web development']:

            if heading:
                primary_category = get_tech_from_heading(heading)
            # primary_category = get_primary_essence(description)
                print(f"primary category: {primary_category}")
                if primary_category != '""':
                    sheet_domains = get_domain_from_sheet()

                    # step 2 - getting relavant domain name

                    relevant_domain = get_relevant_domain(description, sheet_domains)
                    print(f"relevant domain: {relevant_domain}")

                    # step 3 - getting all technologies name out of job description

                    technologies = get_technologies(description)
                    print(technologies)

                    # now we have technologies devided into 3 categories - framework , technology (programming language and databases) and other
                    # we can now implement our own logic to fetch websites accordingly

                    matched_websites = match_websites_from_data(
                        primary_category, technologies, relevant_domain)
                    
                else : 
                    if not description:
                        response_data = [{
                        'category': "",
                        'link': "",
                        'description': "",
                        'reason': "",
                        'androidLink': "",
                        'iosLink': "",
                        'appName': "",
                    }, {
                        'category': "",
                        'link': "",
                        'description': "",
                        'reason': "",
                        'androidLink': "",
                        'iosLink': "",
                        'appName': "",
                    }, {
                        'category': "",
                        'link': "",
                        'description': "",
                        'reason': "",
                        'androidLink': "",
                        'iosLink': "",
                        'appName': "",
                        }]

                        response = {
                            "status": False,
                            "message": "No description provided",
                            "data": response_data
                        }
                        return jsonify(response)
                
                # step 1 - getting essence out of job description
                    primary_category = get_primary_essence(description)
                    print(f"primary category: {primary_category}")

                    if not primary_category.strip():
                        return jsonify({
                            "status": False,
                            "message": "Unable to fetch example for this job description",
                            "data": []
                        })

                    sheet_domains = get_domain_from_sheet()

                    # step 2 - getting relavant domain name

                    relevant_domain = get_relevant_domain(description, sheet_domains)
                    print(f"relevant domain: {relevant_domain}")

                    # step 3 - getting all technologies name out of job description

                    technologies = get_technologies(description)
                    print(technologies)

                    # now we have technologies devided into 3 categories - framework , technology (programming language and databases) and other
                    # we can now implement our own logic to fetch websites accordingly

                    matched_websites = match_websites_from_data(
                        primary_category, technologies, relevant_domain)
                    
                    # descriptions = {}
                    # if matched_websites:
                    #         descriptions = generate_description(
                    #         [website["Website"] for website in matched_websites])
            response_data = [
                        {'prompt': "", 'link': '', 'description': '', 'reason': "", 'androidLink': "", 'iosLink': "", 'appName': ""},
                        {'prompt': "", 'link': '', 'description': '', 'reason': "", 'androidLink': "", 'iosLink': "", 'appName': ""},
                        {'prompt': "", 'link': '', 'description': '', 'reason': "", 'androidLink': "", 'iosLink': "", 'appName': ""}
                    ]
            domain_found = False
            if not matched_websites:
                sheet_data = load_sheet_data()
                # print(sheet_data)
                for row in sheet_data:
                    if row and row[1].lower().strip() == relevant_domain.lower().strip():
                        domain_found = True
                        # Extract the website URLs from the row
                        websites = [row[i] for i in range(2, len(row), 2)]
                        break
                
                if domain_found:
                    # Filter out NaN, None, or null values
                    matched_websites = [website for website in websites if website and website.strip().lower() not in ['nan', 'none', 'null']]
                    if matched_websites:
                        iterations = 3
                        for item in matched_websites * iterations:
                            data = {
                            'prompt': Category,
                            'link': item,
                            'description': "",
                            'reason': "",
                            'androidLink': "",
                            'iosLink': "",
                            'appName': "",
                            }
                            response_data.append(data)
                        response_data = response_data[-3:]
                        response = {
                        "status": True,
                        "message": "Data Fetched Successfully",
                        "data": response_data
                        }
                        return jsonify(response)
                        # descriptions = generate_description(valid_websites)  # Print or process the valid website URLs
                    else:
                        print("Domain name not found in the sheet.")

            if not matched_websites:
                data = {
                        'prompt': Category,
                        'link': "",
                        'description': "",
                        'reason': "",
                        'androidLink': "",
                        'iosLink': "",
                        'appName': "",
                    }
                response_data.append(data)
                data = {
                        'prompt': Category,
                        'link': "",
                        'description': "",
                        'reason': "",
                        'androidLink': "",
                        'iosLink': "",
                        'appName': "",
                    }
                response_data.append(data)
                data = {
                        'prompt': Category,
                        'link': "",
                        'description': "",
                        'reason': "",
                        'androidLink': "",
                        'iosLink': "",
                        'appName': "",
                    }
                response_data.append(data)
                response_data = response_data[-3:]
                response = {
                    "status": True,
                    "message": "Data Fetched Successfully",
                    "data": response_data
                }
                return jsonify(response)
            else:
                # for website, description in descriptions.items():
                    # domain = ""
                for ws in matched_websites:
                        # if ws["Website"] == website:
                        #     domain = ws["Domain Name"]
                        #     break
                    data = {
                        'prompt': Category,
                        'link': ws['Website'],
                        'description': "",
                        'reason': "",
                        'androidLink': "",
                        'iosLink': "",
                        'appName': "",
                    }
                    response_data.append(data)
                response_data = response_data[-3:]
                response = {
                    "status": True,
                    "message": "Data Fetched Successfully",
                    "data": response_data
                }
                return jsonify(response)
        
        if Category.lower() == "mobile development":
            domain = get_domain(description)
            ratings_index = check_ratings(domain)
            Information = get_description(ratings_index, description)
            response_data = [
                {'prompt': Category, 'link': '', 'description': '', 'reason': "", 'androidLink': "", 'iosLink': "", 'appName': ""},
                {'prompt': Category, 'link': '', 'description': '', 'reason': "", 'androidLink': "", 'iosLink': "", 'appName': ""},
                {'prompt': Category, 'link': '', 'description': '', 'reason': "", 'androidLink': "", 'iosLink': "", 'appName': ""}
                            ]
            for index_number, data in Information.items():
                
                ioslink = data.get('Apple Link', '')
                androidlink=data.get('Google Link', '') 
                url=data.get('Website', '')
                appname = data.get('App Name', '')
                brief = data.get('Description', '')

                data = {
                    'prompt': Category,
                    'link': url,
                    'description': brief,
                    'reason': "",
                    'androidLink': androidlink if androidlink else "",
                    'iosLink': ioslink if ioslink else "",
                    'appName': appname if appname else "",
                }
                response_data.append(data)
            response_data = response_data[-3:]
            print(response_data)
            response = {
                "status":True,
                "message":"data fetched successfully",
                "data":response_data
            }
            return jsonify(response)
        if Category.strip() == "":
                response = {
                    "status":True,
                    "message":"Unable to fetch example for this job description",
                    "data":[]
                }
                return jsonify(response)

    except Exception as e:
        print("An error occurred during request handling:")
        print(e)  # Print the full traceback
        abort(500, "Unable to fetch data for this job description!")

    # Error handlers

@app.errorhandler(400)
def bad_request(error):
    print("Bad request:", error.description)
    response = {
        "status": False,
        "message": error.description,
        "data": []
    }
    return jsonify(response), 400

@app.errorhandler(404)
def not_found(error):
    print("Resource not found: ", error.description)
    response = {
        "status": False,
        "message": "Resource not found",
        "data": []
    }
    return jsonify(response), 404

@app.errorhandler(500)
def internal_server_error(error):
    print("Unable to fetch data for this job description!", traceback.format_exc())
    response = {
        "status": False,
        "message": "Unable to fetch data for this job description!",
        "data": []
    }
    return jsonify(response), 500

@app.errorhandler(400)
def bad_request(error):
    print("Bad request:", error.description)
    response = {
        "status": False,
        "message": error.description,
        "data": []
    }
    return jsonify(response), 400

def get_google_search_urls(url):
    headers = {"User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    search_results = soup.find_all()
    urls = []

    for i,result in enumerate(search_results):
        link = result.find("a")
        if link is not None:
            if 'https' in link['href']:
                regex=(link['href'].replace("/url?q=", "")).split('&')[0]
                if regex not in urls:
                    urls.append(regex)
    return urls[:3]

@app.route('/fetch_linkedin_links', methods=['POST'])
def get_urls():
        data = request.get_json()
        search_url = data.get('search_url')
        urls = get_google_search_urls(search_url)
        return jsonify({'urls': urls})

@app.route('/get-email', methods=['POST'])
def get_email():
    url = "https://api.apollo.io/api/v1/people/bulk_match"
    request_data = request.get_json()

    data = {
        "api_key": "o3PCdAlkXPgMtTfWZqzajw",
        "reveal_personal_emails": True,
        "details": [
            {
                "first_name": request_data.get("first_name"),
                "last_name": request_data.get("last_name"), 
                "linkedin_url": request_data.get("linkedin_url")

            }
        ]
    }

    headers = {
        'Cache-Control': 'no-cache',
        'Content-Type': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, json=data)

    try: 
        data = response.json()
        matches = data.get('matches', [])
        if matches:
                match = matches[0]
                email = match.get('email')
                organization = match.get('organization', {})
                organization_id = organization.get('id')
                organization_name = organization.get('name')
                state = match.get('state')
                city = match.get('city')
                country = match.get('country')
                website_url = organization.get('website_url')
                primary_domain = organization.get('primary_domain')
                estimated_num_employees = organization.get('estimated_num_employees')
                title = match.get('title')


        return jsonify({'status':True, 'email': email, 'organization_id':organization_id, 'organization_name':organization_name, 'state':state, 'city':city, 'country':country, 'website_url':website_url,'primary_domain':primary_domain, 'estimated_num_employee':estimated_num_employees, 'title':title }), 200
    except:
        return jsonify({'status':False, 'message':'invalid email id'}), 200



if __name__ == '__main__':
    # logger.info("Starting Flask application...")
    app.run(host='0.0.0.0', port=6969, debug=False)
