#How to run the backend app 
#Activate the virtual environment
source myenv/bin/activate
#Run the redis Server 
redis-server
#This command is used to run the background worker
celery -A study_app worker --loglevel=info
#Run the python django server in a new terminal 
python manage.py runserver
swagger documentation type  http://localhost:8000/swagger/ in your browser 

cd /Users/asoribabackend/Downloads/study_app
source myenv/bin/activate
daphne -b 0.0.0.0 -p 8000 study_app.asgi:application

docker compose exec studyapp_django python manage.py createsuperuser