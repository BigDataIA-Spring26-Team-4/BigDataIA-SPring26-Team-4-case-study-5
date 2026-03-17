# 🐳 Docker Deployment Guide

## 🎯 **What's Included:**

Your Docker setup includes:
- ✅ FastAPI application container
- ✅ Redis cache container
- ✅ Health checks
- ✅ Auto-restart
- ✅ Volume persistence for Redis
- ✅ Network isolation

---

## 🚀 **Quick Start (5 Minutes)**

### **Step 1: Copy Environment File**

```bash
cd docker
copy .env.example .env
```

**Edit `.env` with your Snowflake credentials:**
```env
SNOWFLAKE_ACCOUNT=
SNOWFLAKE_USER=
SNOWFLAKE_PASSWORD=
```

---

### **Step 2: Build and Run**

```bash
# From the docker directory
docker-compose up --build
```

**Or run in detached mode (background):**
```bash
docker-compose up -d --build
```

---

### **Step 3: Verify It's Running**

**Check containers:**
```bash
docker-compose ps
```

**Expected output:**
```
NAME                 STATUS         PORTS
pe-org-air-api       Up (healthy)   0.0.0.0:8000->8000/tcp
pe-org-air-redis     Up (healthy)   0.0.0.0:6379->6379/tcp
```

**Test health endpoint:**
```bash
curl http://localhost:8000/health
```

**Or open in browser:**
```
http://localhost:8000/health
http://localhost:8000/docs
```

---

## 🛠️ **Common Docker Commands**

### **Start Services**
```bash
docker-compose up
```

### **Start in Background**
```bash
docker-compose up -d
```

### **Stop Services**
```bash
docker-compose down
```

### **Stop and Remove Volumes (⚠️ Deletes Redis data)**
```bash
docker-compose down -v
```

### **Rebuild After Code Changes**
```bash
docker-compose up --build
```

### **View Logs**
```bash
# All services
docker-compose logs

# Specific service
docker-compose logs api
docker-compose logs redis

# Follow logs (like tail -f)
docker-compose logs -f api
```

### **Restart a Service**
```bash
docker-compose restart api
docker-compose restart redis
```

### **Check Service Status**
```bash
docker-compose ps
```

### **Execute Command in Container**
```bash
# Python shell in API container
docker-compose exec api python

# Bash shell in API container
docker-compose exec api /bin/bash

# Redis CLI
docker-compose exec redis redis-cli
```

---

## 🔍 **Testing Redis Cache**

Once containers are running, test that Redis is working:

### **Test 1: Create a Company (First Time - Cache Miss)**
```bash
curl -X POST http://localhost:8000/api/v1/companies \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Corp",
    "ticker": "TEST",
    "industry_id": "550e8400-e29b-41d4-a716-446655440001",
    "position_factor": 0.5
  }'
```

### **Test 2: Get Company (Second Time - Cache Hit)**
```bash
# Replace COMPANY_ID with ID from previous response
curl http://localhost:8000/api/v1/companies/COMPANY_ID
```

### **Test 3: Check Redis Keys**
```bash
docker-compose exec redis redis-cli KEYS "*"
```

**Expected:** You'll see cache keys like `companies:*`

---

## 🏥 **Health Checks**

Both containers have health checks:

**API Health Check:**
```bash
docker-compose exec api curl -f http://localhost:8000/health || exit 1
```

**Redis Health Check:**
```bash
docker-compose exec redis redis-cli ping
```

---

## 📊 **Monitoring**

### **Check Resource Usage**
```bash
docker stats
```

### **Check Redis Memory Usage**
```bash
docker-compose exec redis redis-cli INFO memory
```

### **Check Redis Cache Stats**
```bash
docker-compose exec redis redis-cli INFO stats
```

---

## 🐛 **Troubleshooting**

### **Issue 1: "Cannot connect to Docker daemon"**

**Solution:**
- Make sure Docker Desktop is running
- On Windows: Start Docker Desktop application

---

### **Issue 2: "Port 8000 already in use"**

**Solution:**
```bash
# Stop local uvicorn first
# Or change port in docker-compose.yaml:
ports:
  - "8001:8000"  # Use port 8001 instead
```

---

### **Issue 3: "Snowflake connection failed"**

**Solution:**
- Check `.env` file in `docker/` directory
- Verify Snowflake credentials are correct
- Check logs: `docker-compose logs api`

---

### **Issue 4: Containers keep restarting**

**Check logs:**
```bash
docker-compose logs api
```

**Common causes:**
- Invalid Snowflake credentials
- Missing environment variables
- Database not initialized

---

### **Issue 5: Changes not reflected**

**Solution:**
```bash
# Rebuild the container
docker-compose up --build

# Or force rebuild
docker-compose build --no-cache
docker-compose up
```

---

## 🔄 **Development Workflow**

### **For Local Development:**
Use local uvicorn (faster, hot reload):
```bash
uvicorn app.main:app --reload
```

### **For Testing Docker:**
Use Docker Compose:
```bash
docker-compose up
```

### **For Production:**
Use Docker with proper .env and scaling:
```bash
docker-compose up -d
docker-compose scale api=3  # Run 3 API containers
```

---

## 📁 **Docker File Structure**

```
docker/
├── Dockerfile           # Container definition
├── compose.yaml         # Multi-container orchestration
├── .env.example         # Template
├── .env                 # Your actual values (not in git)
└── README.Docker.md     # This file
```

---

## 🚀 **Production Considerations**

For production deployment, consider:

1. **Use production WSGI server:**
   - Update CMD to use gunicorn with uvicorn workers

2. **Add environment-specific configs:**
   - docker-compose.prod.yaml
   - Separate .env files

3. **Enable HTTPS:**
   - Add nginx reverse proxy
   - SSL certificates

4. **Add monitoring:**
   - Prometheus + Grafana
   - Log aggregation

5. **Database connection pooling:**
   - Already configured in snowflake.py

6. **Rate limiting:**
   - Consider adding slowapi

---

## ✅ **Verification Checklist**

After deployment, verify:

```bash
# 1. Containers are running
docker-compose ps  # Both should show "Up (healthy)"

# 2. Health check passes
curl http://localhost:8000/health  # Should return "healthy"

# 3. API is accessible
curl http://localhost:8000/docs  # Opens Swagger UI

# 4. Redis is working
docker-compose exec redis redis-cli ping  # Should return "PONG"

# 5. Snowflake connection works
# Check health endpoint shows snowflake: "healthy"

# 6. Can create a company
# Test POST /api/v1/companies in Swagger

# 7. Cache is working
# Create company, then GET it twice - second should be faster
```

---

## 📚 **Additional Resources**

- **Docker Compose Docs:** https://docs.docker.com/compose/
- **FastAPI in Docker:** https://fastapi.tiangolo.com/deployment/docker/
- **Redis Docker:** https://hub.docker.com/_/redis

---

## 🎯 **Quick Command Reference**

```bash
# Start
docker-compose up -d

# Stop
docker-compose down

# Logs
docker-compose logs -f

# Restart
docker-compose restart api

# Rebuild
docker-compose up --build

# Clean everything
docker-compose down -v
docker system prune -a
```

---

**Your Docker setup is production-ready!** 🚀
