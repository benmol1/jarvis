# Docker Deployment for Jarvis Backend

This document describes how to deploy the Jarvis backend on a Raspberry Pi using Docker.

## Prerequisites

### On the Raspberry Pi:
1. **Raspberry Pi OS** (64-bit recommended for Docker)
2. **Docker installed**
   ```bash
   # Install Docker on Raspberry Pi
   curl -fsSL https://get.docker.com | sh
   sudo usermod -aG docker $USER
   newgrp docker  # or log out and back in
   
   # Install Docker Compose
   sudo apt install docker-compose-plugin
   ```

3. **Tailscale installed** (for remote access from iPhone)
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```
   Note your Tailscale hostname (e.g., `jarvis-pi.tailnet-name.ts.net`)

## Setup

### 1. Clone the repository
```bash
cd ~
git clone <your-repo-url> jarvis
cd jarvis/backend
```

### 2. Create environment file
```bash
cp .env.example .env
# Edit .env and add your Anthropic API key
nano .env
```

The `.env` file should contain:
```
ANTHROPIC_API_KEY=your-anthropic-api-key-here
```

### 3. Create data directory and profile
```bash
mkdir -p data
# Create your profile
cp about_ben.example.md data/about_ben.md
nano data/about_ben.md
```

### 4. Build and run
```bash
# Build the image
docker compose build

# Start the container
docker compose up -d

# Check status
docker compose ps
docker compose logs -f
```

### 5. Test locally
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello Jarvis"}'
```

### 6. Test from iPhone
Update `ContentView.swift` on your iPhone to use your Pi's Tailscale hostname:
```swift
private let backendURL = URL(string: "http://jarvis-pi:8000/chat")!
```

Then test the app.

## Docker Commands

| Command | Description |
|---------|-------------|
| `docker compose build` | Build the image |
| `docker compose up -d` | Start container in background |
| `docker compose down` | Stop and remove container |
| `docker compose restart` | Restart container |
| `docker compose ps` | Show running containers |
| `docker compose logs -f` | View logs in real-time |
| `docker compose exec jarvis-backend sh` | Enter container shell |
| `docker system prune` | Clean up unused images/volumes |

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | - | Your Anthropic API key |
| `JARVIS_PROFILE_PATH` | No | `/data/about_ben.md` | Path to profile file |
| `JARVIS_STATE_PATH` | No | `/data/state.json` | Path to state file |

### Volumes

The following directories are mounted as volumes for persistence:
- `./data:/data` - Contains `about_ben.md` and `state.json`
- `./about_ben.md:/data/about_ben.md:ro` - Profile file (read-only)

### Ports

- `8000:8000` - HTTP port for the FastAPI server

## Troubleshooting

### ARM compatibility issues
The Dockerfile uses multi-stage builds with `python:3.11-slim` for building and `python:3.11-alpine` for runtime, both of which support ARM64 (Raspberry Pi 4/5) and ARMv7 (Raspberry Pi 3/Zero 2).

If you get architecture errors, ensure you're using a 64-bit OS on your Pi.

### Permission issues
If the container can't write to mounted volumes:
```bash
# Ensure the data directory has correct permissions
chmod -R 755 data
```

### Health check failing
The health check endpoint is at `/health`. Test it directly:
```bash
curl http://localhost:8000/health
```

### Port already in use
If port 8000 is taken:
```bash
# Find and kill the process
sudo lsof -i :8000
kill <PID>

# Or change the port in docker-compose.yml
```

## Updating

To update to the latest code:
```bash
cd ~/jarvis/backend
git pull
docker compose down
docker compose build
docker compose up -d
```

## Architecture Notes

- **Multi-stage build**: Reduces final image size by copying only the virtual environment from the builder stage
- **Alpine base**: Small footprint, good for ARM devices
- **Non-root user**: Runs as `jarvis` user for security
- **Health check**: Automatically restarts if container becomes unresponsive
- **Persistent volumes**: Profile and state survive container restarts
