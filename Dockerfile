FROM node:18-alpine

# Set the working directory inside the container
WORKDIR /app

# Copy all project files into the container
COPY . .

# Install dependencies
RUN npm install

# Build the application (if a build script is defined)
RUN npm run build

# Expose the default port (adjust if your app uses a different port)
EXPOSE 3000

# Define the default command to run the app (modify as needed for your start script)
CMD ["npm", "start"]
