module.exports = {
  apps: [
    {
      name: 'max-flask',
      cwd: './',
      script: 'venv/bin/gunicorn',
      args: 'app:app --bind 0.0.0.0:5000 --workers 2 --threads 4 --timeout 120',
      interpreter: 'none',
      env: {
        FLASK_ENV: 'production',
        BAILEYS_URL: 'http://localhost:3001'
      }
    },
    {
      name: 'max-baileys',
      cwd: './baileys',
      script: 'index.js',
      interpreter: 'node',
      env: {
        FLASK_URL: 'http://localhost:5000/message'
      },
      max_restarts: 10,
      restart_delay: 5000
    }
  ]
}
