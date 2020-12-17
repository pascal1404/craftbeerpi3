from flask import json, request
from flask_classy import FlaskView, route
from git import Repo, Git
import sqlite3
from modules.app_config import cbpi
from werkzeug.utils import secure_filename
import pprint
import time
import os
import sys
from modules.steps import Step,StepView

class MMuMJSONImport(FlaskView):
    MMUM_JSON_FILE = "./upload/mmum.json"
    @route('/', methods=['GET'])
    def get(self):
        if not os.path.exists(self.MMUM_JSON_FILE):
            self.api.notify(headline="File Not Found", message="Please upload a json-File from MMuM",
                            type="danger")
            return ('', 404)
        result = []
        e = json.load(open(self.MMUM_JSON_FILE))
        result.append({"id": 1, "name": e['Name']})
        self.load(1)
        return json.dumps(result)

    def allowed_file(self, filename):
        return '.' in filename and filename.rsplit('.', 1)[1] in set(['json'])

    @route('/upload', methods=['POST'])
    def upload_file(self):
        try:
            if request.method == 'POST':
                file = request.files['file']
                if file and self.allowed_file(file.filename):
                    file.save(os.path.join(self.api.app.config['UPLOAD_FOLDER'], "mmum.json"))
                    self.api.notify(headline="Upload Successful", message="The json-file was uploaded succesfully")
                    return ('', 204)
                return ('', 404)
        except Exception as e:
            self.api.notify(headline="Upload Failed", message="Failed to upload json-file", type="danger")
            return ('', 500)

    @route('/<int:id>', methods=['POST'])
    def load(self, id):

        name = self.getRecipeName(id)
        self.api.set_config_parameter("brew_name", name)
        steps = self.getSteps(id)
        first_wort_hops = self.getFirstWortHops(id)
        hops = self.getBoilAlerts(id)
        boil_time = self.getBoilTime(id)
        mashstep_type = cbpi.get_config_parameter("step_mash", "MashStep")
        mash_kettle = cbpi.get_config_parameter("step_mash_kettle", None)
        mash_in_temp = self.getMashin(id)
        mash_out_temp = self.getMashout(id)

        boilstep_type = cbpi.get_config_parameter("step_boil", "BoilStep")
        boil_kettle = cbpi.get_config_parameter("step_boil_kettle", None)
        boil_temp = 100 if cbpi.get_config_parameter("unit", "C") == "C" else 212
        # READ KBH DATABASE
        Step.delete_all()
        StepView().reset()

        try:
            if 'modules.plugins.cbpi-SimpleUtilitySteps' in sys.modules:
                Step.insert(**{"name": "Clear Logs", "type": "SimpleClearLogsStep", "config": {}})
            Step.insert(**{"name": "Mash in", "type": "MashInStep", "config": {"kettle": mash_kettle, "temp": mash_in_temp}})
            for row in steps:
                Step.insert(**{"name": row.get("name"), "type": mashstep_type, "config": {"kettle": mash_kettle, "temp": float(row.get("temp")), "timer": row.get("timer")}})
            if 'modules.plugins.TelegramPushNotifications' in sys.modules:
                Step.insert(**{"name": "Iodine Test", "type": "IodineStep", "config": {"kettle": mash_kettle, "temp": 72, "timer": 10}})
            Step.insert(**{"name": "Mash out", "type": "MashInStep", "config": {"kettle": mash_kettle, "temp": mash_out_temp}})
            if 'modules.plugins.cbpi-SimpleUtilitySteps' in sys.modules:
                if first_wort_hops is not "":
                    Step.insert(**{
                            "name": "first wort hopping", 
                            "type": "SimpleManualStep", 
                            "config": {
                                "heading": "first wort hopping", 
                                "message": "Adding these hops to the boiling kettle:\n" + first_wort_hops + "\n press next button!",
                                "notifyType": "success",
                                "proceed": "Pause"
                            }
                        })
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
                "name": "Boiling",
                "type": boilstep_type,
                "config": {
                    "kettle": boil_kettle,
                    "temp": boil_temp,
                    "temp_diff": 3,
                    "timer": boil_time,
                    ## The model supports seven boil-time additions.
                    ## Set the rest to None to signal them being absent
                    "hop_1": hops[0]["time"] if len(hops) >= 1 else None,
                    "hop_2": hops[1]["time"] if len(hops) >= 2 else None,
                    "hop_3": hops[2]["time"] if len(hops) >= 3 else None,
                    "hop_4": hops[3]["time"] if len(hops) >= 4 else None,
                    "hop_5": hops[4]["time"] if len(hops) >= 5 else None,
                    "hop_6": hops[5]["time"] if len(hops) >= 6 else None,
                    "hop_7": hops[6]["time"] if len(hops) >= 7 else None,
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

    def findMax(self, id, string):
        e = json.load(open(self.MMUM_JSON_FILE))
        for idx in range(1,20):
            search_string = string.replace("%%",str(idx))
            i = idx
            if search_string not in e:
                break
        return i

    def getRecipeName(self, id):
        #e = xml.etree.ElementTree.parse(self.MMUM_JSON_FILE).getroot()
        e = json.load(open(self.MMUM_JSON_FILE))
        return e['Name']

    def getBoilTime(self, id):
        #e = xml.etree.ElementTree.parse(self.MMUM_JSON_FILE).getroot()
        e = json.load(open(self.MMUM_JSON_FILE))
        return float(e['Kochzeit_Wuerze'])

    def getMashin(self, id):
        #e = xml.etree.ElementTree.parse(self.MMUM_JSON_FILE).getroot()
        e = json.load(open(self.MMUM_JSON_FILE))
        return float(e['Infusion_Einmaischtemperatur'])

    def getMashout(self, id):
        #e = xml.etree.ElementTree.parse(self.MMUM_JSON_FILE).getroot()
        e = json.load(open(self.MMUM_JSON_FILE))
        return float(e['Abmaischtemperatur'])

    def getFirstWortHops(self, id):
        e = json.load(open(self.MMUM_JSON_FILE))
        str=""
        for idx in range(1,self.findMax(id,"Hopfen_VWH_%%_Sorte")):
            if idx > 1:
                str = str + " and "
            name = "%sg %s %s%% alpha" % (e["Hopfen_VWH_{}_Menge".format(idx)],e["Hopfen_VWH_{}_Sorte".format(idx)],e["Hopfen_VWH_{}_alpha".format(idx)])
            str = str + name
        return str

    def getBoilAlerts(self, id):
        e = json.load(open(self.MMUM_JSON_FILE))
        hops = []
        for idx in range(1,self.findMax(id,"Hopfen_%%_Kochzeit")):
            name = "%sg %s %s%% alpha" % (e["Hopfen_{}_Menge".format(idx)],e["Hopfen_{}_Sorte".format(idx)],e["Hopfen_{}_alpha".format(idx)])
            if e["Hopfen_{}_Kochzeit".format(idx)].isnumeric():
                alert = float(e["Hopfen_{}_Kochzeit".format(idx)])
            elif e["Hopfen_{}_Kochzeit".format(idx)] == "Whirlpool":
                alert = float(1)
            else:
                self.api.notify(headline="No Number at Hoptime", message="Please change json-File at Hopfen_{}_Kochzeit".format(idx), type="danger")
                alert = float(1)
            hops.append({"name":name,"time":alert})
            
        for idx in range(1,self.findMax(id,"WeitereZutat_Wuerze_%%_Kochzeit")):
            name = "%s%s %s" % (e["WeitereZutat_Wuerze_{}_Menge".format(idx)],e["WeitereZutat_Wuerze_{}_Einheit".format(idx)],e["WeitereZutat_Wuerze_{}_Name".format(idx)])
            if e["WeitereZutat_Wuerze_{}_Kochzeit".format(idx)].isnumeric():
                alert = float(e["WeitereZutat_Wuerze_{}_Kochzeit".format(idx)])
            elif e["WeitereZutat_Wuerze_{}_Kochzeit".format(idx)] == "Whirlpool":
                alert = float(1)
            else:
                self.api.notify(headline="No Number at Hoptime", message="Please change json-File at WeitereZutat_Wuerze_{}_Kochzeit".format(idx), type="danger")
                alert = float(1)
            hops.append({"name":name,"time":alert})
            

        ## Dedupe and order the additions by their time, to prevent multiple alerts at the same time
        hops = sorted(hops, key = lambda i: i['time'], reverse=True)

        return hops

    def getSteps(self, id):
        e = json.load(open(self.MMUM_JSON_FILE))
        steps = []
        for idx in range(1,self.findMax(id,"Infusion_Rastzeit%%")):
            if self.api.get_config_parameter("unit", "C") == "C":
                temp = float(e["Infusion_Rasttemperatur{}".format(idx)])
            else:
                temp = round(9.0 / 5.0 * float(e["Infusion_Rasttemperatur{}".format(idx)]) + 32, 2)

            steps.append({"name": "Rast {}".format(idx), "temp": temp, "timer": float(e["Infusion_Rastzeit{}".format(idx)])})

        return steps

@cbpi.initalizer()
def init(cbpi):

    MMuMJSONImport.api = cbpi
    MMuMJSONImport.register(cbpi.app, route_base='/api/mmum')
