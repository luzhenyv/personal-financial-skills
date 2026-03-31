import re

def clean_subtitle(file_path, output_path):
    # Read the subtitle file
    with open(file_path, 'r', encoding='ISO-8859-1') as file:
        subtitle_content = file.read()

    # Remove all non-relevant tags (anything between < >)
    cleaned_subtitle = re.sub(r'<[^>]+>', '', subtitle_content)

    # Remove non-ASCII characters and control characters
    cleaned_subtitle = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', cleaned_subtitle)

    # Remove extra spaces and newlines, keep only necessary ones
    cleaned_subtitle = re.sub(r'\s+', ' ', cleaned_subtitle)

    # Write the cleaned subtitle content to a new file
    with open(output_path, 'w', encoding='utf-8') as output_file:
        output_file.write(cleaned_subtitle)

    print(f"Cleaned subtitle saved to: {output_path}")

# Example usage
file_path = 'bbc kenneth clarks civilisation - 05 - the hero as artist.English.smi'  # Replace with your subtitle file path
output_path = 'cleaned_subtitle.txt'  # Replace with the desired output file path

clean_subtitle(file_path, output_path)