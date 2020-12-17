from flask import json, request
from flask_classy import FlaskView, route
from git import Repo, Git
import sqlite3
from modules.app_config import cbpi
from werkzeug.utils import secure_filename
import pprint
import time
import os
from modules.steps import Step,StepView
import xml.etree.ElementTree

class BeerXMLImport(FlaskView):
    BEER_XML_FILE = "./upload/beer.xml"
    @route('/', methods=['GET'])
    def get(self):
        if not os.path.exists(self.BEER_XML_FILE):
            self.api.notify(headline="File Not Found", message="Please upload a Beer.xml File",
                            type="danger")
            return ('', 404)
        result = []

        e = xml.etree.ElementTree.parse(self.BEER_XML_FILE).getroot()
        result = []
        for idx, val in enumerate(e.findall('RECIPE')):
            result.append({"id": idx+1, "name": val.find("NAME").text})
        return json.dumps(result)

    def allowed_file(self, filename):
        return '.' in filename and filename.rsplit('.', 1)[1] in set(['xml'])

    @route('/upload', methods=['POST'])
    def upload_file(self):
        try:
            if request.method == 'POST':
                file = request.files['file']
                if file and self.allowed_file(file.filename):
                    file.save(os.path.join(self.api.app.config['UPLOAD_FOLDER'], "beer.xml"))
                    self.api.notify(headline="Upload Successful", message="The Beer XML file was uploaded succesfully")
                    return ('', 204)
                return ('', 404)
        except Exception as e:
            self.api.notify(headline="Upload Failed", message="Failed to upload Beer xml", type="danger")
            return ('', 500)

    @route('/<int:id>', methods=['POST'])
    def load(self, id):


        steps = self.getSteps(id)
        hops = self.getBoilAlerts(id)
        name = self.getRecipeName(id)
        self.api.set_config_parameter("brew_name", name)
        boil_time = self.getBoilTime(id)
        mashstep_type = cbpi.get_config_parameter("step_mash", "MashStep")
        mash_kettle = cbpi.get_config_parameter("step_mash_kettle", None)

        boilstep_type = cbpi.get_config_parameter("step_boil", "BoilStep")
        boil_kettle = cbpi.get_config_parameter("step_boil_kettle", None)
        boil_temp = 100 if cbpi.get_config_parameter("unit", "C") == "C" else 212

        # READ KBH DATABASE
        Step.delete_all()
        StepView().reset()

        try:
            if 'modules.plugins.cbpi-SimpleUtilitySteps' in sys.modules:
                Step.insert(**{"name": "Clear Logs", "type": "SimpleClearLogsStep", "config": {}})
            for row in steps:
                Step.insert(**{"name": row.get("name"), "type": mashstep_type, "config": {"kettle": mash_kettle, "temp": float(row.get("temp")), "timer": row.get("timer")}})
            if 'modules.plugins.TelegramPushNotifications' in sys.modules:
                Step.insert(**{"name": "Iodine Test", "type": "IodineStep", "config": {"kettle": mash_kettle, "temp": 72, "timer": 10}})
            Step.insert(**{"name": "ChilStep", "type": "ChilStep", "config": {"timer": 45}})
            if 'modules.plugins.cbpi-SimpleUtilitySteps' in sys.modules:
                Step.insert(**{
                    "name": "Measure Original Gravity", 
                    "type": "SimpleManualStep", 
                    "config": {
                        "heading": "Measure Original Gravity", 
                        "message": "what is the original gravity of the beer wort?",
                        "notifyType": "success",
                        "proceed": "Pause"
                    }
                })
            ## Add boiling step
            Step.insert(**{
                "name": "Boil",
                "type": boilstep_type,
                "config": {
                    "kettle": boil_kettle,
                    "temp": boil_temp,
                    "temp_diff": 3,
                    "timer": boil_time,
                    ## Beer XML defines additions as the total time spent in boiling,
                    ## CBP defines it as time-until-alert

                    ## Also, The model supports five boil-time additions.
                    ## Set the rest to None to signal them being absent
                    "hop_1": boil_time - hops[0]["time"] if len(hops) >= 1 else None,
                    "hop_2": boil_time - hops[1]["time"] if len(hops) >= 2 else None,
                    "hop_3": boil_time - hops[2]["time"] if len(hops) >= 3 else None,
                    "hop_4": boil_time - hops[3]["time"] if len(hops) >= 4 else None,
                    "hop_5": boil_time - hops[4]["time"] if len(hops) >= 5 else None,
                    "hop_6": boil_time - hops[5]["time"] if len(hops) >= 6 else None,
                    "hop_7": boil_time - hops[6]["time"] if len(hops) >= 7 else None,
                    "hop_1_desc": hops[0]["name"]if len(hops) >= 1 else None,
                    "hop_2_desc": hops[1]["name"]if len(hops) >= 2 else None,
                    "hop_3_desc": hops[2]["name"]if len(hops) >= 3 else None,
                    "hop_4_desc": hops[3]["name"]if len(hops) >= 4 else None,
                    "hop_5_desc": hops[4]["name"]if len(hops) >= 5 else None,
                    "hop_6_desc": hops[5]["name"]if len(hops) >= 6 else None,
                    "hop_7_desc": hops[6]["name"]if len(hops) >= 7 else None
                }
            })
            if 'modules.plugins.cbpi-SimpleUtilitySteps' in sys.modules:
                Step.insert(**{
                    "name": "Measure Original Gravity", 
                    "type": "SimpleManualStep", 
                    "config": {
                        "heading": "Measure Original Gravity", 
                        "message": "what is the original gravity of the beer wort?",
                        "notifyType": "success",
                        "proceed": "Pause"
                    }
                })
            ## Add Whirlpool step
            Step.insert(**{"name": "Whirlpool", "type": "ChilStep", "config": {"timer": 15}})
            if 'modules.plugins.cbpi-SimpleUtilitySteps' in sys.modules:
                Step.insert(**{"name": "Save Logs", "type": "SimpleSaveLogsStep", "config": {}})
            StepView().reset()
            self.api.emit("UPDATE_ALL_STEPS", Step.get_all())
            self.api.notify(headline="Recipe %s loaded successfully" % name, message="")
        except Exception as e:
            self.api.notify(headline="Failed to load Recipe", message=e.message, type="danger")
            return ('', 500)

        return ('', 204)

    def getRecipeName(self, id):
        e = xml.etree.ElementTree.parse(self.BEER_XML_FILE).getroot()
        return e.find('./RECIPE[%s]/NAME' % (str(id))).text

    def getBoilTime(self, id):
        e = xml.etree.ElementTree.parse(self.BEER_XML_FILE).getroot()
        return float(e.find('./RECIPE[%s]/BOIL_TIME' % (str(id))).text)

    def getBoilAlerts(self, id):
        e = xml.etree.ElementTree.parse(self.BEER_XML_FILE).getroot()

        recipe = e.find('./RECIPE[%s]' % (str(id)))
        hops = []
        for e in recipe.findall('./HOPS/HOP'):
            use = e.find('USE').text
            ## Hops which are not used in the boil step should not cause alerts
            if use != 'Aroma' and use != 'Boil':
                continue
            
            name = "%sg %s %s%% alpha" % (e.find('AMOUNT').text,e.find('NAME').text,e.find('ALPHA').text)
            alert = float(e.find('TIME').text)
            
            hops.append({"name":name,"time":alert})

        ## There might also be miscelaneous additions during boild time
        for e in recipe.findall('MISCS/MISC[USE="Boil"]'):
            alert = float(e.find('TIME').text)
            name = "%sg %s" % (e.find('AMOUNT').text,e.find('NAME').text)
            hops.append({"name":name,"time":alert})

        ## Dedupe and order the additions by their time, to prevent multiple alerts at the same time
        hops = sorted(hops, key = lambda i: i['time'], reverse=True)

        return hops

    def getSteps(self, id):
        e = xml.etree.ElementTree.parse(self.BEER_XML_FILE).getroot()
        steps = []
        for e in e.findall('./RECIPE[%s]/MASH/MASH_STEPS/MASH_STEP' % (str(id))):
            if self.api.get_config_parameter("unit", "C") == "C":
                temp = float(e.find("STEP_TEMP").text)
            else:
                temp = round(9.0 / 5.0 * float(e.find("STEP_TEMP").text) + 32, 2)

            steps.append({"name": e.find("NAME").text, "temp": temp, "timer": float(e.find("STEP_TIME").text)})

        return steps

@cbpi.initalizer()
def init(cbpi):

    BeerXMLImport.api = cbpi
    BeerXMLImport.register(cbpi.app, route_base='/api/beerxml')
