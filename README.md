**Work to be done**

> Data cleaning. rn the XMl file is uncleanmakes the elasticsearch index larger, slower, less accurate
> optimize  the elastic search mappings. an index with strict mapping.
> custom page rank because current isn't good
> Make a script that automates the entire process. Currently have to put in commands myself
> add fault tolerance by making multiple nodes with replication
> write a benchmarking script to actually prove the system scales as data and load increases

**work related to spark that needs to be done**
> use bulk sizing
> disable ES refresh
> align partitions for load balancing


**Text Cleaning**
> only keep articles with namespace 0
> use `<id>` as unique `_id`
> 


**commands to run project**
***Ignore everything below. just run the `run_pipeline.ps1`***
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


Stats on small dataset(before elastic search update 1):
no#  workers  cores_per_worker   Ram_per_worker  time
1     1           12               6             5:30
2     3           3                2             4:30
3     3           4                3             4:00
4     3           4                4             4:30 😭


Stats on small dataset(after elastic search update 1):
no#  workers  cores_per_worker   Ram_per_worker  time
4     3           4                4             4:00 
1     1           12               10            3:48   0:54 to clean data
2     3           4                3.2           4:18   1.1 to clean data
3     3           4                3             4:00


