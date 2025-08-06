# Kundenportal-Sydoc

--🔨-------WIP-------🚧-------WIP-------🔨-------WIP-------🚧-------WIP-------🔨-------WIP-------🚧-----
------------------The Application and Documentation is a WORK IN PROGRESS
--🔨-------WIP-------🚧-------WIP-------🔨-------WIP-------🚧-------WIP-------🔨-------WIP-------🚧-----

A modern Flask-based customer portal for document workflow management, providing secure authentication and comprehensive workitem tracking for multiple client organizations.

## 🚀 Features

### 🔐 Authentication & Security

- **Secure Login System** with bcrypt password hashing
- **Rate Limiting** (5 login attempts per minute, 200 requests per day)
- **Session Management** with secure cookies and automatic expiration
- **Scope-based Access Control** for multi-tenant architecture

### 📊 Dashboard

- **Real-time Statistics** showing document processing status
- **Interactive Progress Tracking** with visual workflow indicators
- **Client-specific Data** filtered by user scope

### 📋 Workitems Management

- **Comprehensive Overview** of all workitems with detailed information
- **Advanced Filtering** by status, priority, and custom search
- **Sortable Columns** for better data organization
- **Export Functionality** to CSV
- **Real-time Status Updates** with color-coded indicators
- **Request for Processing** by client for prioritized processing

## 🛠️ Technology Stack

- **Backend**: Flask (Python)
- **Database**: Microsoft SQL Server with pyodbc
- **Frontend**: HTML5, Tailwind CSS, JavaScript
- **Authentication**: bcrypt for password hashing
- **Rate Limiting**: Flask-Limiter
- **Environment**: python-dotenv for configuration

## 📁 Project Structure

```
Kundenportal-Sydoc/
├── app.py                          # Main Flask application
├── README.md                       # Project documentation
├── .env                           # Environment variables (not in repo)
├── static/
│   └── images/                    # Client logos and icons
│       ├── ElektroMaterial-Icon.png
│       ├── Privera-Icon.png
│       └── StadtBiel-Icon.svg
├── templates/
│   ├── index.html                 # Login page
│   ├── post_login.html           # Dashboard
│   └── workitems_overview.html   # Workitems management
└── sql/
    └── dps-activities.sql         # Database schema/queries
```

## 🗄️ Database Schema

### Core Tables

- **`Users`** - User authentication and scope assignment
- **`t_WorkItems`** - Main workitem tracking table
- **`t_ActivityInstances`** - Workflow activity instances
- **`t_Processes`** - Process definitions and client mapping

### Key Views

- **`v_StadtBiel_LatestState`** - Latest state aggregation for StadtBiel client

## 🔗 API Endpoints

| Route         | Method    | Description                        |
| ------------- | --------- | ---------------------------------- |
| `/`           | GET       | Redirect to login page             |
| `/login`      | GET, POST | User authentication                |
| `/logout`     | GET       | User logout                        |
| `/post_login` | GET       | Dashboard (requires auth)          |
| `/workitems`  | GET       | Workitems overview (requires auth) |

## 👥 Multi-Client Support

The portal supports multiple client organizations. At the moment the following:

- **ElektroMaterial** - Electrical materials processing
- **Privera** - Private document management
- **StadtBiel** - Municipal document processing

Each client has:

- Dedicated data isolation
- Custom branding (logos/icons)
- Specific workflow configurations
- Independent statistics tracking

## 🚀 Deployment

### Production Considerations

- Use a proper WSGI server (Gunicorn, uWSGI)
- Configure SSL/TLS certificates
- Set up database connection pooling
- Implement proper logging
- Configure environment-specific settings

### Example Production Setup

```bash
# Install Gunicorn
pip install gunicorn

# Run with Gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature / style / chore / ... branch (`git checkout -b feature/xy`)
3. Commit your changes (`git commit -m 'Add this and that'`)
4. Push to the branch (`git push origin feature/xy`)
5. Open a Pull Request

## 📄 License

This project is proprietary software owned by Sydoc-Code.

---

**Built with ❤️ by the Sydoc Team**
