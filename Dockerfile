# Stage 1: Extract mcp-contrast jar from Contrast's official image
FROM contrast/mcp-contrast:1.0.0 AS mcp-contrast

# Stage 2: Final image
FROM python:3.13-slim

# Install Node.js (for filesystem MCP server) and JRE 17 (for Contrast MCP server)
RUN apt-get update && \
    apt-get install -y --no-install-recommends nodejs npm default-jre-headless && \
    rm -rf /var/lib/apt/lists/*

# Pre-install filesystem MCP at build time — no runtime npm fetch (supply chain fix)
RUN npm install -g @modelcontextprotocol/server-filesystem@2026.1.14

# Copy Contrast MCP jar from stage 1
COPY --from=mcp-contrast /app/app.jar /opt/mcp-contrast/mcp-contrast.jar
ENV MCP_CONTRAST_JAR_PATH=/opt/mcp-contrast/mcp-contrast.jar

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

ENTRYPOINT ["python", "-m", "module_identifier"]
