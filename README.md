# Divine Davis - Personal Portfolio Website

My personal portfolio website showcasing my work as a Product and Program Manager at JPMorgan Chase.

## 🌐 Live Site
http://167.7.170.219

## 📁 Structure
- `index.html` - Home page with bio
- `portfolio.html` - Project showcase
- `resume.html` - Professional experience
- `style.css` - Styling
- `profile.jpg` - Profile photo

## 🚀 Auto-Deployment
This website automatically deploys to my DigitalOcean server every 5 minutes via cron job.

### Setup on Server:
```bash
curl -s https://raw.githubusercontent.com/divinedavis/Personal-Website/main/setup_server.sh | bash
```

### Manual Deployment:
```bash
/root/auto_deploy_website.sh
```

### View Logs:
```bash
tail -f /var/log/website-deploy.log
```

## 💻 Local Development
1. Clone the repository
2. Edit files
3. Commit and push
4. Changes appear on website within 5 minutes

## 📧 Contact
- Email: divinejdavis@gmail.com
- LinkedIn: [linkedin.com/in/divinejdavis](https://www.linkedin.com/in/divinejdavis)
- GitHub: [github.com/divinedavis](https://github.com/divinedavis)
