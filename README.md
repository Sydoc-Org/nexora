# Kundenportal-Sydoc

--🔨-------WIP-------🚧-------WIP-------🔨-------WIP-------🚧-------WIP-------🔨-------WIP-------🚧-----
------------------The Application and Documentation is a WORK IN PROGRESS
--🔨-------WIP-------🚧-------WIP-------🔨-------WIP-------🚧-------WIP-------🔨-------WIP-------🚧-----

A modern Flask-based customer portal for document workflow management, providing secure authentication, comprehensive workitem tracking, and multi-client support.

## 🚀 Features

### 🔐 Authentication & Security

- Secure login with bcrypt password hashing
- Rate limiting (5 login attempts/minute, 200 requests/day)
- Session management with secure cookies and expiration
- Scope-based access control for multi-tenant architecture

### 📊 Dashboard

- Real-time statistics and document processing status
- Interactive progress tracking with workflow indicators
- Client-specific data filtered by user scope

### 📋 Workitems Management

- Overview of all workitems with detailed info
- Advanced filtering by status, priority, and search
- Sortable columns for data organization
- Export to CSV
- Real-time status updates with color indicators
- Request for prioritized processing

### 🌗 Dark Mode

- Toggleable dark mode using Tailwind CSS
- Remembers user preference across sessions

### 📝 Logging & Auditing

- Logs all user actions for auditing and troubleshooting
- Tracks login, workitem views, exports, and more

## 🛠️ Technology Stack

- **Backend:** Flask (Python)
- **Database:** Microsoft SQL Server (pyodbc)
- **Frontend:** HTML5, Tailwind CSS, JavaScript
- **Authentication:** bcrypt
- **Rate Limiting:** Flask-Limiter
- **Environment:** python-dotenv

## 📁 Project Structure

```
Kundenportal-Sydoc/
├── app.py                      # Main Flask application
├── README.md                   # Project documentation
├── .env                        # Environment variables (excluded from repo)
├── static/
│   ├── images/                 # Client logos and icons
│   ├── utils.js                # Shared JS utilities (logging, etc.)
│   ├── workitems_overview.js   # Workitems page logic
│   └── post_login.js           # Dashboard page logic
├── templates/
│   ├── index.html              # Login page
│   ├── post_login.html         # Dashboard
│   ├── workitems_overview.html # Workitems management
│   ├── profile.html            # User profile/settings
│   ├── _header.html            # Shared header/navigation
│   └── _base.html              # Shared base template
└── sql/
    └── dps-activities.sql      # Database schema and queries
```

## 🗄️ Database Schema

### Core Tables

- **Users**: User authentication and scope assignment
- **t_WorkItems**: Main workitem tracking
- **t_ActivityInstances**: Workflow activity instances
- **t_Processes**: Process definitions and client mapping
- **User_Logs**: User action logging

### Key Views

- **v_StadtBiel_LatestState**: Latest state aggregation for StadtBiel client

## 🔗 API Endpoints

| Route         | Method    | Description                        |
| ------------- | --------- | ---------------------------------- |
| `/`           | GET       | Redirect to login page             |
| `/login`      | GET, POST | User authentication                |
| `/logout`     | GET       | User logout                        |
| `/post_login` | GET       | Dashboard (requires auth)          |
| `/workitems`  | GET       | Workitems overview (requires auth) |
| `/profile`    | GET       | User profile/settings              |
| `/log_action` | POST      | Log user actions (internal)        |

## 👥 Multi-Client Support

Supports multiple client organizations:

- **ElektroMaterial**: Electrical materials processing
- **Privera**: Private document management
- **StadtBiel**: Municipal document processing

Each client has:

- Data isolation
- Custom branding (logos/icons)
- Specific workflow configurations
- Independent statistics tracking

## 🌗 Dark Mode

- Toggle dark mode via header button
- Uses Tailwind CSS `dark:` classes
- Persists user preference with localStorage

## 📝 Logging

- All user actions (login, view, export, demand, etc.) are logged to `User_Logs`
- Logs include user, action type, resource, details, IP, and timestamp

## 🚀 Deployment

### Production Considerations

- Use a WSGI server (Gunicorn, uWSGI)
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
2. Create a feature/style/chore branch (`git checkout -b feature/xy`)
3. Commit your changes (`git commit -m 'Add this and that'`)
4. Push to the branch (`git push origin feature/xy`)
5. Open a Pull Request

## 📄 License

This project is proprietary software owned by Sydoc-Code.

---

**Built with ❤️ by the Sydoc Team**
