import json
import boto3
import boto3.session
import random

# Class to deploy the IaC in AWS
class IaC_Deployment():
    def __init__(self, event, context):
        self.event = event
        self.context = context
        
        self.account_id = boto3.client('sts').get_caller_identity().get('Account')
        
        self.Parameters = []
        self.stack_name = ""
        self.bucketname = ""
        self.iac_key = ""
        
		# Get Stack Name
        if "IaC_Name" in self.event:
            self.stack_name = self.event["IaC_Name"]
            
		# Get Region Name
        if "region_name" in self.event.keys():
            print (self.event["region_name"])
            region_name = self.event["region_name"]
        else:
            region_name = "us-east-1"
            
        if "ApplicationParameters" in self.event:
            self.Parameters = self.event["ApplicationParameters"]
        
        if "IaCParameters" in self.event:
            self.bucketname = self.event["IaCParameters"]["BucketName"]
            self.iac_key = self.event["IaCParameters"]["CloudformationKey"]
        
        my_session = boto3.session.Session()
        self.client_s3 = my_session.client('s3')
		
		
		# Assume Role from Master account to child account to deploy the teplate if the account number of the IaC platform and Child account is different.
        if  "Account_Number" in self.event and self.event["Account_Number"] != self.account_id:
            print ("Change Account ARN")
            self.session_client = boto3.session.Session()
            self.sts_master_client = self.session_client.client('sts')
            self.child_account_session_name = "ChildAccountSession-" + str(random.randint(1, 100000))
            self.master_account_session_name = "MasterAccountSession-" + str(random.randint(1, 100000))
            self.iam_arn_string_1 = "arn:aws:iam::"
            self.child_account_role_arn = self.iam_arn_string_1 + str(self.event["Account_Number"]) + ":role/iac_child_role"
            self.master_account_role_arn = self.iam_arn_string_1 + str(self.account_id) + ":role/iac_admin_role"
            master_account_role_creds = self.sts_master_client.assume_role(RoleArn=self.master_account_role_arn,
															   RoleSessionName=self.master_account_session_name)
            master_credentials = master_account_role_creds.get('Credentials')
            master_access_key_id = master_credentials.get('AccessKeyId')
            master_secret_access_key = master_credentials.get('SecretAccessKey')
            master_session_token = master_credentials.get('SessionToken')
            self.master_assume_role_session = boto3.Session(master_access_key_id, master_secret_access_key,
															master_session_token)												   
			

            child_account_role_creds = self.sts_master_client.assume_role(RoleArn=self.child_account_role_arn,
															  RoleSessionName=self.child_account_session_name)
            child_credentials = child_account_role_creds.get('Credentials')
            child_access_key_id = child_credentials.get('AccessKeyId')
            child_secret_access_key = child_credentials.get('SecretAccessKey')
            child_session_token = child_credentials.get('SessionToken')
            self.child_assume_role_session = boto3.Session(child_access_key_id, child_secret_access_key,
														   child_session_token)
            self.client_cloudformation = self.child_assume_role_session.client('cloudformation',region_name=region_name)
            self.account_id = self.event["Account_Number"]
        else:
            print ("No Account change")
            print (self.account_id)
            my_session = boto3.session.Session(region_name = region_name) 
            self.client_cloudformation = my_session.client('cloudformation')
            
        self.region_name = region_name
        
    # Get the cloudformation template form S3
    def get_iac_template(self):
        try:
            response = self.client_s3.get_object(
				Bucket=self.bucketname,
				Key=self.iac_key ,
				ResponseContentType='text/vnd.yaml')
            filedata = response['Body'].read()
            filedata = filedata.decode("utf-8") 
            return True, filedata
        except Exception as e:
            print (str(e))
            return False, Str(e)
    
	# Update the IaC cloudformation template
    def update_cloudformation(self,content):
        try:
            response = self.client_cloudformation.update_stack(
                StackName=self.stack_name,
                TemplateBody=content,
                Parameters = self.Parameters,
                Capabilities=[
                    'CAPABILITY_IAM',
                    'CAPABILITY_NAMED_IAM',
                ],
                
                Tags=[
                    {
                        'Key': 'iac_platform_resource',
                        'Value': 'yes'
                    },
                ],
                RoleARN="arn:aws:iam::"+self.account_id+":role/iac_child_role"
            )
            return "Infrastructure As Code Deployment Updation is initiated, In the AWS Account "+ str(self.account_id) +" in the Region "+self.region_name
                
        except Exception as e:
            print (str(e))
            return str(e)

	# Deploy the IaC cloudformation template
    def deploy_cloudformation(self):
        try:
            status, stacks_list_response = self.list_cloudformation_stacks()
            if (status == True):
                status, content = self.get_iac_template()
                if status == True:
                    if self.stack_name not in stacks_list_response:
                        print ("Create Stack")
                        response = self.client_cloudformation.create_stack(
                            StackName=self.stack_name,
                            TemplateBody=content,
                            TimeoutInMinutes=120,
                            Parameters = self.Parameters,
                            Capabilities=[
                                'CAPABILITY_IAM',
                                'CAPABILITY_NAMED_IAM',
                            ],
                            
                            Tags=[
                                {
                                    'Key': 'iac_platform_resource',
                                    'Value': 'yes'
                                },
                            ],
                            RoleARN="arn:aws:iam::"+self.account_id+":role/iac_child_role"
                        )
                        return "Infrastructure As Code Deployment Creation is initiated, In the AWS Account "+ str(self.account_id) +" in the Region "+self.region_name
                    else:
                        # Update Stack
                        print ("Update Stack")
                        response = self.update_cloudformation(content)
                        return response
                else:
                    return content
               
            else:
                return stacks_list_response
        except Exception as e:
            print (str(e))
            return str(e)
            
	# Check if the CFT Stack exists already.
    def list_cloudformation_stacks(self):
        print ("List Stacks")
        try:
            response = self.client_cloudformation.list_stacks(
                StackStatusFilter=[
                    'CREATE_IN_PROGRESS','CREATE_FAILED','CREATE_COMPLETE','ROLLBACK_IN_PROGRESS','ROLLBACK_FAILED','ROLLBACK_COMPLETE','DELETE_IN_PROGRESS','DELETE_FAILED',
                    'UPDATE_IN_PROGRESS','UPDATE_COMPLETE_CLEANUP_IN_PROGRESS','UPDATE_COMPLETE','UPDATE_ROLLBACK_IN_PROGRESS','UPDATE_ROLLBACK_FAILED',
                    'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS','UPDATE_ROLLBACK_COMPLETE','REVIEW_IN_PROGRESS','IMPORT_IN_PROGRESS','IMPORT_COMPLETE','IMPORT_ROLLBACK_IN_PROGRESS',
                    'IMPORT_ROLLBACK_FAILED','IMPORT_ROLLBACK_COMPLETE',
                ]
            )
            
            stack_list = []
            for stack_detail in response['StackSummaries']:
                    stack_list.append(stack_detail['StackName'])

            while(True):
                
                if ('NextToken' in response.keys() and response['NextToken'] != None):
                    print (response)
                    next_token = response['NextToken']
                else:
                    break
                
                 
                response = self.client_cloudformation.list_stacks(
                    NextToken=next_token,
                    StackStatusFilter=[
                        'CREATE_IN_PROGRESS','CREATE_FAILED','CREATE_COMPLETE','ROLLBACK_IN_PROGRESS','ROLLBACK_FAILED','ROLLBACK_COMPLETE','DELETE_IN_PROGRESS','DELETE_FAILED',
                        'UPDATE_IN_PROGRESS','UPDATE_COMPLETE_CLEANUP_IN_PROGRESS','UPDATE_COMPLETE','UPDATE_ROLLBACK_IN_PROGRESS','UPDATE_ROLLBACK_FAILED',
                        'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS','UPDATE_ROLLBACK_COMPLETE','REVIEW_IN_PROGRESS','IMPORT_IN_PROGRESS','IMPORT_COMPLETE','IMPORT_ROLLBACK_IN_PROGRESS',
                        'IMPORT_ROLLBACK_FAILED','IMPORT_ROLLBACK_COMPLETE',
                    ]
                )
                for stack_detail in response['StackSummaries']:
                    stack_list.append(stack_detail['StackName'])
                        
            print (stack_list)
            
            return True, stack_list
        except Exception as e:
            print (str(e))
            return False, str(e)
            
#Lambda Function will initiate from here.
def lambda_handler(event, context):
    # TODO implement
    try:
        
        iac_development = IaC_Deployment(event, context)
        response = iac_development.deploy_cloudformation()
        print (response)
        return {
            'statusCode': 200,
            'body': response
        }
    except Exception as e:
        return {
            'statusCode': 200,
            'body': str(e)
        }
    

