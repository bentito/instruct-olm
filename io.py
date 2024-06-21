#!/usr/bin/env python3

import os
import subprocess
import tarfile
import shutil
import argparse
from openai import OpenAI

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


def run_command(command):
    """Run a shell command and return the output."""
    print(f"Running command: {command}")
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Command succeeded with output:\n{result.stdout}")
    else:
        print(f"Command failed with error:\n{result.stderr}")
    return result.stdout.strip()


def extract_files(temp_location, target_dir, filenames):
    """Extract specific files from tar.gz archives in the temporary location."""
    for root, dirs, files in os.walk(temp_location):
        for file in files:
            if file.endswith(".tar.gz"):
                file_path = os.path.join(root, file)
                with tarfile.open(file_path, "r:gz") as tar:
                    for member in tar.getmembers():
                        if any(fn in member.name for fn in filenames):
                            tar.extract(member, target_dir)


def read_file_contents(file_path):
    """Read and return the contents of a file."""
    with open(file_path, 'r') as file:
        return file.read()


def main():
    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument('--no-gpt', action='store_true', help='Do not query GPT model')
    args = parser.parse_args()

    # Get the running insights operator pod
    insights_operator_pod = run_command(
        "oc get pods --namespace=openshift-insights -o custom-columns=:metadata.name --no-headers --field-selector=status.phase=Running")

    # Define the temporary location for unpacking files
    temp_location = "/tmp/insights-operator"

    # Copy insights files from the pod to the temporary location
    run_command(f"oc cp openshift-insights/{insights_operator_pod}:/var/lib/insights-operator {temp_location}")

    # Define target directory and filenames to extract
    target_dir = "/tmp/extracted_insights"
    filenames_to_extract = ["gathers.json", "olm_operators"]

    # Create the target directory if it doesn't exist
    os.makedirs(target_dir, exist_ok=True)

    # Extract the relevant files
    extract_files(temp_location, target_dir, filenames_to_extract)

    # Gather file contents for GPT-4 analysis
    gathers_json_content = read_file_contents(os.path.join(target_dir, "insights-operator/gathers.json"))
    olm_operators_content = read_file_contents(os.path.join(target_dir, "config/olm_operators.json"))

    if args.no_gpt:
        # Print the file contents using jq for pretty-printing, debug
        print("Gathers.json Content:")
        jq_process = subprocess.Popen(['jq', '.'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        gathers_output, _ = jq_process.communicate(input=gathers_json_content)
        print(gathers_output)

        print("\nOLM Operators Configuration Content:")
        jq_process = subprocess.Popen(['jq', '.'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        olm_output, _ = jq_process.communicate(input=olm_operators_content)
        print(olm_output)
    else:
        # Define the prompt for GPT-4
        prompt = {
            "role": "system",
            "content": f"""
        Analyze the following OpenShift cluster insights data and summarize any findings that a cluster admin would find interesting:

        Gathers.json:
        {gathers_json_content}

        OLM Operators Configuration:
        {olm_operators_content}
        """}

        # Query the GPT-4 model with the prompt
        response = client.chat_completions.create(model="gpt-4", messages=[prompt])

        # Print the response from GPT-4
        print(response.choices[0].message.content)

    # Clean up the temporary files
    shutil.rmtree(temp_location)
    shutil.rmtree(target_dir)


if __name__ == "__main__":
    main()
