# Resource finder for user
def findlink(query):
    # query = message.text
    with open('function\output.txt', 'r') as file:
        lines = file.readlines()
        for line in lines:
            if query in line:
                return line
    return "Sorry, I couldn't find any link for your query."

# query = input("Enter your query: ")
# print(findlink(query))