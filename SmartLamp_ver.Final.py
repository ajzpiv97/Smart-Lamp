import serial
import sys
import glob
import RPi.GPIO as IO
import time
import os
from os import path
import itertools
import pandas as pd
import pyowm
import json
import requests
import thingspeak
import socket
from datetime import datetime


class NoDataRead(Exception):
    def __init__(self, data):
        self.data = data
        
    def __str__(self):
        return repr(self.data)
    
class MappingError(Exception):
    def __init__(self, data):
        self.data = data
        
    def __str__(self):
        return repr(self.data)

class InvalidTimeInput(Exception):
    def __init__(self, data):
        self.data = data
        
    def __str__(self):
        return repr(self.data)
    

def serial_ports():
    """ Lists serial port names

        :raises EnvironmentError:
            On unsupported or unknown platforms
        :returns:
            A list of the serial ports available on the system
    """
    if sys.platform.startswith('win'):
        ports = ['COM%s' % (i + 1) for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        # this excludes your current terminal "/dev/tty"
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/tty.*')
    else:
        raise EnvironmentError('Unsupported platform')

    result = []
    for port in ports:
        try:
            s = serial.Serial(port)
            s.close()
            result.append(port)
        except (OSError, serial.SerialException):
            pass
    return result


def voltage_serial(ports):
    voltage_list = []
    flag = 0
    for port in ports:
        try:
            ser = serial.Serial(port, 9600, timeout=1)
            ser.flush()
            start_time = time.time()
            while True:
                if ser.in_waiting > 0:
                    line = float(ser.readline().decode('utf-8').rstrip())
                    #print(line, 'bits')
                    voltage_list.append(line)
                try:   
                    if time.time() - start_time > 25:
                        raise NoDataRead("Read time cannot take more 33 seconds")
                except NoDataRead as e:
                    print ("Received error:", e.data)
                    break
                
                if len(voltage_list)>21:
                    voltage_list= voltage_list[1:-1]
                    flag = 1
                    break
            break
        except OSError:
            print("No serial connection with port = ", port)
        
    return voltage_list, flag

def average(voltage_values):
    try:
        if len(voltage_values)==0:
            raise NoDataRead("No data was read from the SPI")
    except NoDataRead as e:
        print ("Received error:", e.data)
        voltage_values = voltage_serial(ports)
        if len(voltage_values)==0:
            print("Check connection to SPI device")
            return
    return int(sum(voltage_values)/len(voltage_values))


def mapping(input_start, input_end, output_start, output_end, voltage):
    output =  output_start + ((output_end - output_start) / (input_end - input_start)) * (voltage - input_start)
    try:
        if not (output_start<=output<=output_end):
            raise MappingError("Mapped value is not within the desired range")
    except NoDataRead as e:
        print ("Received error:", e.data)
        # Try again
        output = mapping(input_start, input_end, output_start, output_end, voltage)
        if not output_start<=output<=output_end:
            print("Error in bounds")
            return
    return output

def photoresistor_Range(value):
    # Room Light is Minimum
    if 0<=value<=33:
        value = 100
        print("Set Led to High")
        
    # Room Light is Medium
    elif 33<value<=66:
        value = 50
        print("Set Led to Medium")
        
    # Room Light is Medium/High
    elif 66<value<=100:
        value = 0
        print("Set Led to Off")
        
    return value

def createAlarm():
    hour, min, day = 0,0,0
    local_time = time.localtime(time.time())
    pass_flag = 0
    print('If want to cancel press ctl + c')
    while True:
        while True:

            try:
                hour = int(input("Print Hour in 24hours Scale (Midnight is 0): "))
                if not -1 < hour < 24:
                    raise InvalidTimeInput("Value is not within 0-23")
                pass_flag = 1
                break
        
            except InvalidTimeInput as e:
                print ("Received error:", e.data)
                pass
            except KeyboardInterrupt:
                print('Interrupted')
                break
            except ValueError:
                print("Value entered not a number")
                pass


        if pass_flag==1:
            while True:
                try:
                    min = int(input("Print Minutes Multiples of 10: "))
                    if (not -1< min < 61) or min%10!=0:
                        raise InvalidTimeInput("Value is not within 0-60")
                    pass_flag = 2
                    break
                except InvalidTimeInput as e:
                    print ("Received error:", e.data)
                    pass
                
                except KeyboardInterrupt:
                    print('Interrupted')
                    break
                
                except ValueError:
                    print("Value entered not a number")
                    pass
            
        if pass_flag==2:
            while True:
                try:
                    day = int(input("Print day 0 being Monday and 6 is Sunday: "))
                    if not -1< day < 7:
                        raise InvalidTimeInput("Value is not within 0-6")
                    pass_flag = 3
                    break
                    
                except InvalidTimeInput as e:
                    print ("Received error:", e.data)
                    pass
                
                except KeyboardInterrupt:
                    print('Interrupted')
                    break
                
                except ValueError:
                    print("Value entered not a number")
                    pass
        
        if pass_flag==3:
            t = (local_time.tm_year, local_time.tm_mon, local_time.tm_mday,
                 hour, min, 0, day, 0, 0)
            return time.strptime(time.asctime(t), "%a %b %d %H:%M:%S %Y")
        
        finished_flag = input('If Finished Type 1 else press any key: ')
        if finished_flag=='1':
            return finished_flag
        
def createDataFrame(alarm):
    headers = ['Hour', 'Minute', 'Week_Day']
    df = pd.DataFrame(alarm, columns = headers)
    print(df)
    return df

def createCSV(df, path):
    df.to_csv(path, sep=',', encoding='utf-8', index=False)
    return path

def openCSV(path):
    df = pd.read_csv(path, sep =',', usecols=['Week_Day', 'Hour','Minute'])
    return df

def convert_to_list(df):
    return df.values.tolist()

def checkDuplicates(list1):
    flag = 0
    list1.sort()
    new_list = list(i for i,_ in itertools.groupby(list1))
    if len(new_list) != len(list1):
        flag=1
        return new_list, flag
    else:   
        return new_list, flag

def setup_weatherAPI():
    json_data = 0
    try:
        api_key = 'b24f242112ab2a5b4cff7d50ae875dae'
        owm = pyowm.OWM(api_key)
        # Get Local IP Address Information
        local_ip = 'https://extreme-ip-lookup.com/json/'
        r = requests.get(local_ip)
        data = json.loads(r.content.decode())
        if owm.is_API_online():
    # Get Weather based on latitude and longitud
            api_call = 'http://api.openweathermap.org/data/2.5/weather?'+'lat='+str(float(data.get('lat'))) + \
                '&lon=' +str(float(data.get('lon'))) + '&appid=' + api_key
            #api_call = 'http://api.openweathermap.org/data/2.5/weather?'+'lat=36.246618' + \
                #'&lon=-116.8169955' + '&appid=' + api_key
            json_data = requests.get(api_call).json()

        return json_data
    except: 
        print('Invalid API Key. Please try again!')

def get_weather_data(data):
    try:
        if data['weather']:
            weather_data = {}
            try:
                temperature = round(data['main']['feels_like']-273.15, 2)
                weather_data['temperature'] = temperature
            except KeyError as e:
                weather_data['temperature'] = 'No data'
                print('No data found for:', e)
                pass
                
            try:
                clouds = data['clouds']['all']
                weather_data['clouds'] = clouds
            except KeyError as e:
                weather_data['clouds'] = "No data"
                print('No data found for:', e)
                pass
            
            try: 
                description = data['weather'][0]['description']
                weather_data['description'] = description
            except KeyError as e:
                weather_data['description'] = 'No data'
                print('No data found for:', e)
                pass
            
            try: 
                rain= data['rain']['1h']
                weather_data['rain'] = rain                
            except KeyError as e:
                weather_data['rain'] = 0
                print('No data found for:', e) 
                pass
            
            try: 
                snow= data['snow']['1h']
                weather_data['snow'] = snow                
            except KeyError as e:
                weather_data['snow'] = 0
                print('No data found for:', e)                    
                pass
            
            try: 
                sunrise_time = [time.localtime(data['sys']['sunrise']).tm_hour,
                                                   time.localtime(data['sys']['sunrise']).tm_min]
                weather_data['sunrise'] = sunrise_time
                                               
            except KeyError as e:
                print('No data found for:', e)
                pass
                
            try: 
                sunset_time = [time.localtime(data['sys']['sunset']).tm_hour,
                                               time.localtime(data['sys']['sunset']).tm_min]
                weather_data['sunset'] = sunset_time
            
            except KeyError as e:
                print('No data found for:', e)
                
            return weather_data
            
    except KeyError:
        print('No data found. Please try again later')

def sendData(channel, flag, val_int, *data):
    try:
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        print("Current Time =", current_time)
        
        if flag ==0:
            val_int = round(val_int*5/1023, 2)
            try:
                response = channel.update({'field5':val_int})
                print(response)
                time.sleep(15)
            except:
                print("connection failed")
                
        else:
            data = data[0]
            print(data)
            try:
                if not isinstance(data['temperature'], str) and not isinstance(data['clouds'], str):
                    val1 = data['temperature']
                    val2 = data['clouds']
                    val3 = data['rain']
                    val4 = data['snow']
                    val5 = round(val_int*5/1023,2)
                    response = channel.update({'field1':val1,'field2':val2,
                                               'field3':val3,
                                                    'field4':val4,
                                                       'field5':val5})
                    print(response)                          
                    time.sleep(15)
                    
                    
                elif isinstance(data['temperature'], str) and not isinstance(data['clouds'], str):
                    val2 = data['clouds']
                    val3 = data['rain']
                    val4 = data['snow']
                    val5 = round(val_int*5/1023,2)
                    response = channel.update({'field2':val2, 'field3':val3,
                                                    'field4':val4,
                                                       'field5':val5})
                    print(response)
                    time.sleep(15)
                    
                elif not isinstance(data['temperature'], str) and  isinstance(data['clouds'], str):
                    val1 = data['temperature']
                    val3 = data['rain']
                    val4 = data['snow']
                    val5 = round(val_int*5/1023,2)
                    response = channel.update({'field1':val1, 'field3':val3,
                                                    'field4':val4,
                                                       'field5':val5})
                    print(response)
                    time.sleep(15)
                else:
                    val3 = data['rain']
                    val4 = data['snow']
                    val5 = round(val_int*5000/1023,2)
                    response = channel.update({'field3':val3,'field4':val4,
                                                       'field5':val5})

                    print(response)
                    time.sleep(15)
            except:
                print("connection failed")

            
    except KeyboardInterrupt:
        print('Interrupted')
                     
        
def main():
    # Variables
    ph_voltage = []
    ports = []
    average_voltage = 0
    active_alarms = []
    mapped_value = 0
    dc_value = 0
    
    file = os.getcwd() +'/Alarms.csv'
    userAlarms = []
    existingDF = 0
    alarmsDF = 0
    all_data = {'clouds': [], 'sunset': [], 'sunrise': [], 'snow':[],
                        'rain':[], 'temperature': [], 'description': [], 'photoresistor':[]}


    # Arduino serial read bit bounds
    arduino_lb = 0
    arduino_ub = 500

    # Dutty Cycle bounds
    dc_lb = 0
    dc_up = 100

    # Raspi Pin
    pwm_pin = 12

    # Flag
    pwm_flag = 1
    time_struct = 0
    light_flag = 0
    active_flag=0
    print_flag = 0
    dupli_flag=0
    send_flag = 0
    read_flag = 0
    photo_flag = 0
    weather_flag = 0
    
    # Initialize PWM
    IO.setwarnings(False)
    IO.setmode(IO.BOARD)
    IO.setup(12, IO.OUT)
    pwm = IO.PWM(12,1000)
    pwm.start(0)

    # Initialize Temperature LEDS
    leds = [38,40]
    IO.setup(leds, IO.OUT, initial=IO.LOW)

    # Thingspeak API Key
    channel_id = '1054814'
    write_key  = 'EXCRCT30P24J5EYR'
    channel = thingspeak.Channel(id=channel_id,api_key=write_key)

    # Weather API
    data = setup_weatherAPI()
    
    # Initialize Alarms 
    if path.exists(file):
        print('File Exists!')
        existingDF = openCSV(file)
        print(existingDF)
        userAlarms = convert_to_list(existingDF)

        print('Create Alarms......')
        while True:
            try:
                time_struct = createAlarm()
                userAlarms.append([time_struct.tm_hour, time_struct.tm_min, time_struct.tm_wday])
                userAlarms, dupli_flag = checkDuplicates(userAlarms)
                if dupli_flag==1:
                    print('Duplicate found. Alarm Deleted!')
                print("Available Alarms: ", userAlarms)              
            except KeyboardInterrupt:
                break
            except AttributeError:
                if time_struct=='1':
                    break
    else:
        print('File Not Found!')
        print('Create Alarms......')
        while True:
            try:
                time_struct = createAlarm()
                userAlarms.append([time_struct.tm_hour, time_struct.tm_min, time_struct.tm_wday])
                userAlarms, dupli_flag = checkDuplicates(userAlarms)
                if dupli_flag==1:
                    print('Duplicate found. Alarm Deleted!')
                print("Available Alarms: ", userAlarms)
                
            except KeyboardInterrupt:
                break
            except AttributeError:
                if time_struct=='1':
                    break
    try:    
        alarmsDF = createDataFrame(userAlarms)
        createCSV(alarmsDF, file)
        active_alarms = []
    except ValueError:
        print('No Active Alarms In File!')
        
    
    print('Start Lamp Brightness Control')
    while True:
        if len(userAlarms)!=0:
            for alarm in userAlarms:
                if (alarm[0]>=(time.localtime().tm_hour) and alarm[1]>(time.localtime().tm_min)):
                    active_alarms.append(alarm)
                    active_alarms, dupli_flag = checkDuplicates(active_alarms)
                    
                    
            
            try:
                if active_flag==1 or ((time.localtime().tm_hour==active_alarms[0][0]) and (time.localtime().tm_min==active_alarms[0][1]) and (0<time.localtime().tm_sec<=5)):

                    if time.localtime().tm_min==1 and active_alarms[0][1]+10==60:
                        print("Alarm Deactivated At Hour:", time.localtime().tm_hour, ' Min:', time.localtime().tm_min)
                        light_flag=0
                        active_flag=0
                        print_flag=0
                        active_alarms.remove(active_alarms[0])
                        
                    elif time.localtime().tm_min<=active_alarms[0][1]+10:
                        if print_flag==0:
                            print_flag=1
                            active_flag=1
                            light_flag = 1
                            print('Lights On!')
                            print("Activate Alarm Hour:", time.localtime().tm_hour, ' Min:', time.localtime().tm_min, ' Stay Active for 10 Min')
                            print(active_alarms)
                            pwm.ChangeDutyCycle(100)
       
                    else:
                        print("Alarm Deactivated At Hour:", time.localtime().tm_hour, ' Min:', time.localtime().tm_min)
                        light_flag=0
                        active_flag=0
                        print_flag=0
                        active_alarms.remove(active_alarms[0])
                
            except IndexError:
                pass
                
           
        if ((time.localtime().tm_min % 3 == 0) and (time.localtime().tm_min !=30)) and (0<=time.localtime().tm_sec<=1) and photo_flag == 1: # Open serial port every 3 min
            time.sleep(1)
            photo_flag=0
            
            print("Reading Photoresistor")
            while True:
                    ports = serial_ports() # Detect USB Serial Ports
                    ph_voltage, read_flag = voltage_serial(ports) # Read arduino data
                    
                    if read_flag == 1:
                        # Flag to verify that data was read from arduino
                        average_voltage = average(ph_voltage) # Average the read values
                        send_flag =0
                        sendData(channel, send_flag, average_voltage)
                        all_data.setdefault('photoresistor',[]).append(round(average_voltage*5/1023,2))
                        mapped_value = mapping(arduino_lb, arduino_ub, dc_lb, dc_up, average_voltage) # Map the values to the desiered range
                        dc_value = photoresistor_Range(mapped_value) # Set mapped value to the correspoding range for dutty cycle
                        

                        # PWM Of LED
                        if light_flag==0 and (not time.localtime().tm_hour==23 and not 0<=time.localtime().tm_hour<6):
                            print("Led Brightness Modulation")
                            pwm.ChangeDutyCycle(dc_value)
                
                        elif time.localtime().tm_hour==23 or 0<=time.localtime().tm_hour<6:
                            
                            print("Lights Off")
                            pwm.ChangeDutyCycle(0)
                            
                    print('Waiting.....')
                    break
                
                
        val = time.localtime().tm_min/10
        if ((time.localtime().tm_min==18) or (time.localtime().tm_min==48) and (30<=time.localtime().tm_sec<31)) or (
                int(str(val)[2]) == 8 and 0 <= time.localtime().tm_sec < 1) and weather_flag==1: # Get weather data from openweather API every modulo 7
            weather_flag=0
            print('Get Weather Data!!!!')
            time.sleep(1)
            json_data = setup_weatherAPI()
            weather_data = get_weather_data(json_data)

            if weather_data['temperature']<=10:
                print('Temperature Very Cold')
                IO.output(leds, [IO.LOW, IO.HIGH])

            if 10<weather_data['temperature']<=20:
                print('Temperature Cold')
                IO.output(leds, [IO.HIGH, IO.LOW])

            if 20<weather_data['temperature']<=30:
                print('Temperature Mild')
                IO.output(leds, [IO.LOW, IO.HIGH])

            if weather_data['temperature']>30:
                print('Temperature Hot')
                IO.output(leds, IO.HIGH)

            send_flag=1
            sendData(channel, send_flag, average_voltage, weather_data)
            
            for key in weather_data:
                all_data.setdefault(key,[]).append(weather_data[key])
            

        if (time.localtime().tm_min + 1) % 3 ==0 and time.localtime().tm_sec==50:
            if time.localtime().tm_min+1==48 or time.localtime().tm_min+1== 18:
                weather_flag = 1
                print('Weather Flag: ', weather_flag)
            
            photo_flag = 1
            print('Photo Flag: ', photo_flag)
            time.sleep(1)

        if (int(str(val)[2]) + 1) == 8 and time.localtime().tm_sec==50:
            weather_flag=1
            print('Weather Flag: ', weather_flag)
            time.sleep(1)

        
if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Exit Program')
        IO.cleanup()
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)

