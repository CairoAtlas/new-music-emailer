# New Music Emailer Lambda Function
AWS Lambda that checks for new music every day, triggered by CloudWatch. It checks based on artists in DynamoDB

A few things about this repository:
* Code is self documented (for the most part)
* The Lambda automatically deploys to AWS with a successful build thanks to travis-ci
* Unit tests are written with pytest and mocking AWS Services with moto
* Packages to build the deployment package and update lambda is with lambda-setuptools
 
