First make sure that docker is running. Then run the docker-compose.yaml using:
```
docker compose up -d     
```
then run this command to feed the `process_wiki.py` file to the elasticsearch:
```
 docker exec -it spark-master /opt/spark/bin/spark-submit \
>>   --master spark://spark-master:7077 \
>>   --packages org.elasticsearch:elasticsearch-spark-30_2.12:8.12.0,com.databricks:spark-xml_2.12:0.17.0 \
>>   /opt/spark/work-dir/scripts/process_wiki.py
```

Then install the python dependencies for elasticsearch. first uninstall these if downloaded:
```
pip uninstall elasticsearch                               
>> pip uninstall elastic-transport
>> pip uninstall urllib3
```
then install this
```
pip install streamlit elasticsearch==7.17.12    
```

then run the streamlit app using:
```
streamlit run app.py
```