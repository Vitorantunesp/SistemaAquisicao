import LDTP_Const
import socket
import time
import numpy
import datetime
import math

MAX_ANSWER_PACKETS = 40
MAX_DEVICES = 8
DEFAULT_TIMEOUT = 50  # 50 * 10 ms
MAX_CHANNELS = 128
SAMP_BUFF_SIZE = 1000000

# ------------------------------------------------------------------
class Param_Data:
    def __init__(self):
        self.ParamNum = 0
        self.IndexI = 0
        self.IndexJ = 0
        self.CountI = 0
        self.CountJ = 0
        self.Size = 4
        self.Values = []

# ------------------------------------------------------------------
class DevInfo:
    def __init__(self):
        self.ConnectionKey = 0
        self.Timestamp = 0
        self.Status = 0
        self.Synced = False
        self.SystemState = 0
        self.Tag = 'Tag'
        self.NumAnInCh = 0
        self.NumPulseCh = 0
        self.NumDigInCh = 0
        self.NumNavCh = 0
        self.NumCalcCh = 0
        self.NumAnOutCh = 0
        self.NumDigOutCh = 0
        self.NumIntCh = 0
        self.NumExtAnCh = 0
        self.NumExtDigCh = 0
        
        self.LastKeepAlive = datetime.datetime.now()

# ------------------------------------------------------------------
class ChInfo:
    def __init__(self):
        self.Name = 'ChName'
        self.Unit = 'Unit'
        self.ChIndex = 0
        self.IsDig = False
        self.HighLim = 1.0
        self.LowLim = -1.0
        self.coefAng = 1.0
        self.coefLin = 0.0
        self.NumBits = 0
        self.BitName = []
        self.BitHigh = []
        self.BitLow = []


# ------------------------------------------------------------------
class LDTPModule:

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    def __init__(self):
        self.__listIPDev = []
        self.__listIPPC = []
        self.__listCommandSocket = []
        self.__listDataSocket = []
        self.__listDev = []
        self.__listAnswer = []

        self.__command_tag = 0
        self.__ansPos = 0

        self.__RunAsThread = False

        self.__samples = []
        for i in range(0, MAX_CHANNELS):
            self.__samples.append(numpy.zeros(SAMP_BUFF_SIZE))
        self.__sampleTime = numpy.zeros(SAMP_BUFF_SIZE) # store the timestamp of the samples

        self.__acqNumCh = [] # number of channels per device
        self.__sampPos = []
        self.__acqLastFrame = []
        self.__sampCount = []
        self.__sampFreq = 0.0
        self.__sampsLost = []

        self.__syncSampCount = 0
        self.__syncSampPos = 0

        self.__acqActive = False

        self.UseAbsoluteTimestamp = True
        self.__startTimestamp = 0

        self.DataConnActive = []
        for i in range(0, MAX_CHANNELS):
            self.DataConnActive.append(False)
        
        
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------



    # ------------------------------------------------------------------
    def OpenConnection(self, devInd, devIp, pcIp):

        if (devInd >= MAX_DEVICES) or (devInd < 0):
            print('OpenConnection: Invalid devInd')
            return False
    
        self.CloseConnection(devInd)

        try:
            auxSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        except OSError as msg:
            print('Error creating socket')
            return False

        try:
            addrAndPort = (pcIp, 0)
            auxSocket.bind(addrAndPort)
        except OSError as msg:
            auxSocket.close()
            auxSocket = None
            print('Error on bind')
            return False

        try:
            addrAndPort = (devIp, LDTP_Const.LDTP_MSG_COMMAND_PORT)
            auxSocket.connect(addrAndPort)
        except OSError as msg:
            auxSocket.close()
            auxSocket = None
            print('Error on connect')
            return False

        auxSocket.settimeout(0)
        auxSocket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 720000)

        if len(self.__listIPDev) < devInd:
            self.__listCommandSocket[devInd] = auxSocket
            self.__listIPDev[devInd] = devIp
            self.__listIPPC[devInd] = pcIp
        else:
            self.__listCommandSocket.append(auxSocket)
            self.__listIPDev.append(devIp)
            self.__listIPPC.append(pcIp)
            self.__listDataSocket.append(None)
            self.__listDev.append(DevInfo())
        
        return True

    # ------------------------------------------------------------------
    def CloseConnection(self, devInd):

        if (devInd >= MAX_DEVICES) or (devInd < 0):
            print('CloseConnection: Invalid devInd')
            return False
        
        self.__CloseDataConnection(devInd)
        if devInd < len(self.__listCommandSocket):
            if self.__listCommandSocket[devInd] != None:
                self.__listCommandSocket[devInd].close()
                self.__listCommandSocket[devInd] = None
                self.__listIPDev[devInd] = 0;
        return True

    # ------------------------------------------------------------------
    def __OpenDataConnection(self, devInd, devIp, pcIp, port):    
        self.__CloseDataConnection(devInd)

        try:
            auxSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        except OSError as msg:
            print('Error creating socket')
            return False

        try:
            addrAndPort = (pcIp, 0)
            auxSocket.bind(addrAndPort)
        except OSError as msg:
            auxSocket.close()
            auxSocket = None
            print('Error on bind')
            return False

        try:
            addrAndPort = (devIp, port)
            auxSocket.connect(addrAndPort)
        except OSError as msg:
            auxSocket.close()
            auxSocket = None
            print('Error on connect')
            return False

        auxSocket.settimeout(0)
        auxSocket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 720000)

        self.__listDataSocket[devInd] = auxSocket
        self.DataConnActive[devInd] = True
        
        return True

    # ------------------------------------------------------------------
    def __CloseDataConnection(self, devInd):

        self.__acqActive = False
        if devInd < len(self.__listCommandSocket):
            if self.__listDataSocket[devInd] != None:
                self.__listDataSocket[devInd].close()
                self.__listDataSocket[devInd] = None
                if (len(self.__acqNumCh) > devInd):
                    self.__acqNumCh[devInd] = 0
                self.DataConnActive[devInd] = False
        return True

    # ------------------------------------------------------------------
    def RequestDataConnection(self, devInd):

        if (devInd >= MAX_DEVICES) or (devInd < 0):
            print('RequestDataConnection: Invalid devInd')
            return False

        if (self.__listCommandSocket[devInd] == None):
            print('RequestDataConnection: Connection closed')
            return False

        if (self.__listDataSocket[devInd] != None):
            self.ReleaseDataConnection(devInd);
    
        packet = LDTP_Const.ldtp_create_packet_dataconnrequest(self.__command_tag)
        sentCommandTag = self.__command_tag
        self.__command_tag += 1

        self.__listCommandSocket[devInd].send(LDTP_Const.ldtp_packet_to_byte_dataconnrequest(packet));

        timeout = DEFAULT_TIMEOUT
        while (timeout > 0):
            if not self.__RunAsThread:
                self.PeriodicHandle()
            ans = self.__GetMessageAnswer(sentCommandTag)
            if (ans != None):
                ansPacket = LDTP_Const.ldtp_byte_to_packet_ack(ans)
                if (ansPacket.ErrorCode != 0):
                    print('RequestDataConnection: Nack ' + str(ansPacket.ErrorCode))
                    return False
                else:
                    specific = LDTP_Const.ldtp_get_specific_from_packet(ans)
                    port = (specific[0]) & 0x0000FFFF
                    self.__listDev[devInd].ConnectionKey = (specific[0] >> 16) & 0x0000FFFF
                    return self.__OpenDataConnection(devInd, self.__listIPDev[devInd], self.__listIPPC[devInd], port)
            
            time.sleep(0.01)
            timeout = timeout - 1
        print('RequestDataConnection: Timeout')
        return False
        
    # ------------------------------------------------------------------
    def ReleaseDataConnection(self, devInd):

        if (devInd >= MAX_DEVICES) or (devInd < 0):
            print('ReleaseDataConnection: Invalid devInd')
            return False

        if (self.__listDataSocket[devInd] == None):
            print('ReleaseDataConnection: Connection closed')
            return False
    
        packet = LDTP_Const.ldtp_create_packet_dataconnrelease(self.__listDev[devInd].ConnectionKey, self.__command_tag)
        sentCommandTag = self.__command_tag
        self.__command_tag += 1

        self.__listDataSocket[devInd].send(LDTP_Const.ldtp_packet_to_byte_dataconnrelease(packet));

        timeout = DEFAULT_TIMEOUT
        while (timeout > 0):
            if not self.__RunAsThread:
                self.PeriodicHandle()
                ans = self.__GetMessageAnswer(sentCommandTag)
            if (ans != None):
                ansPacket = LDTP_Const.ldtp_byte_to_packet_ack(ans)
                if (ansPacket.ErrorCode != 0):
                    print('ReleaseDataConnection: Nack ' + str(ansPacket.ErrorCode))
                    return False
                else:
                    self.__CloseDataConnection(devInd)
                    return True
            
            time.sleep(0.01)
            timeout = timeout - 1

        print('ReleaseDataConnection: Timeout')
        self.__CloseDataConnection(devInd)
        return False

    # ------------------------------------------------------------------
    def DataAcqSetup(self, devInd, sampFreq, channels):

        if (devInd >= MAX_DEVICES) or (devInd < 0):
            print('DataAcqSetup: Invalid devInd')
            return False

        if (len(channels) == 0):
            print('DataAcqSetup: Invalid channels')
            return False

        if (self.__listDataSocket[devInd] == None):
            print('DataAcqSetup: Connection closed')
            return False

        if (self.__acqActive == True):
            print('DataAcqSetup: Acquisition active; cannot change setup')
            return False

        if ((sampFreq // 10) * len(channels)) > 360:
            sampsPerCh = 360 // len(channels)
        else:
            # Floor division of a float still returns float. The LDTP sample
            # count is uint16; keep the frequency itself as floating point.
            sampsPerCh = max(1, int(sampFreq // 10))
            
        self.__sampFreq = sampFreq
        while (len(self.__acqNumCh) <= devInd):
            self.__acqNumCh.append(0)
        self.__acqNumCh[devInd] = len(channels)
    
        packet = LDTP_Const.ldtp_create_packet_dataacqsetup(self.__listDev[devInd].ConnectionKey,
                                                            sampFreq, sampsPerCh, channels, self.__command_tag)
        sentCommandTag = self.__command_tag
        self.__command_tag += 1

        self.__listDataSocket[devInd].send(LDTP_Const.ldtp_packet_to_byte_dataacqsetup(packet));

        timeout = DEFAULT_TIMEOUT
        while (timeout > 0):
            if not self.__RunAsThread:
                self.PeriodicHandle()
            ans = self.__GetMessageAnswer(sentCommandTag)
            if (ans != None):
                ansPacket = LDTP_Const.ldtp_byte_to_packet_ack(ans)
                if (ansPacket.ErrorCode != 0):
                    print('DataAcqSetup: Nack ' + str(ansPacket.ErrorCode))
                    return False
                else:
                    return True
            
            time.sleep(0.01)
            timeout = timeout - 1

        print('DataAcqSetup: Timeout')
        return False

    # ------------------------------------------------------------------
    def StartDataAcquisition(self):
        answered = 0
        error = False
        sentCommandTag = []

        allAnswered = 0
        for i in range(0, len(self.__listIPDev)):
            allAnswered += (1 << i)
    
        if self.UpdateStatusAll() == False:
            return False

        startTimestamp = 0
        for i in range(0, len(self.__listIPDev)):
            if (self.__listDataSocket[i] != None):
                if startTimestamp == 0:
                    startTimestamp = self.__listDev[i].Timestamp
                if (self.__listDev[i].Synced == False):
                    print('Device ' + self.__listDev[i].Tag + ' not synced')
                    return False
                if abs(self.__listDev[i].Timestamp - startTimestamp) > 1:
                    print('Clocks too different')
                    return False

        startTimestamp = startTimestamp + 2


        for i in range(0, len(self.__listIPDev)):
            if (self.__listDataSocket[i] != None):
                packet = LDTP_Const.ldtp_create_packet_startacq(self.__listDev[i].ConnectionKey, startTimestamp, self.__command_tag)
                sentCommandTag.append(self.__command_tag)
                self.__command_tag += 1

                self.__listDataSocket[i].send(LDTP_Const.ldtp_packet_to_byte_startacq(packet));
            else:
                sentCommandTag.append(0)
                answered = answered + (1 << i)


        # initialize acq variables
        for i in range(0, len(self.__listIPDev)):
            if (len(self.__sampPos) <= i):
                self.__sampPos.append(0)
                self.__acqLastFrame.append(0)
                self.__sampCount.append(0)
                self.__sampsLost.append(0)
            else:
                self.__sampPos[i] = 0
                self.__acqLastFrame[i] = 0
                self.__sampCount[i] = 0
                self.__sampsLost[i] = 0

        self.__startTimestamp = 0
        self.__syncSampCount = 0
        self.__syncSampPos = 0

        timeout = DEFAULT_TIMEOUT
        while ((timeout > 0) and (answered != allAnswered)):
            if not self.__RunAsThread:
                self.PeriodicHandle()

            for i in range(0, len(self.__listIPDev)):
                if (answered & (1 << i)) == 0:
                    ans = self.__GetMessageAnswer(sentCommandTag[i])
                    if (ans != None):
                        ansPacket = LDTP_Const.ldtp_byte_to_packet_ack(ans)
                        if (ansPacket.ErrorCode != 0):
                            print('StartDataAcquisition: Nack ' + str(ansPacket.ErrorCode))
                            error = True;
                        else:
                            answered += (1 << i)

            if (error == True):
                break;
            
            time.sleep(0.01)
            timeout = timeout - 1;

        if (timeout == 0):
            self.StopDataAcquisition();
            print('StartDataAcquisition: Timeout')
            return False

        if (error == True):
            # already printed the error
            self.StopDataAcquisition();
            return False

        self.__acqActive = True
        return True

    # ------------------------------------------------------------------
    def StopDataAcquisition(self):
        answered = 0
        error = False
        sentCommandTag = []
        
        allAnswered = 0
        for i in range(0, len(self.__listIPDev)):
            allAnswered += (1 << i)
        
        for i in range(0, len(self.__listIPDev)):
            if (self.__listDataSocket[i] != None):
                packet = LDTP_Const.ldtp_create_packet_stopacq(self.__listDev[i].ConnectionKey, self.__command_tag)
                sentCommandTag.append(self.__command_tag)
                self.__command_tag += 1

                self.__listDataSocket[i].send(LDTP_Const.ldtp_packet_to_byte_stopacq(packet));
            else:
                sentCommandTag.append(0)
                answered = answered + (1 << i)

        timeout = DEFAULT_TIMEOUT
        while ((timeout > 0) and (answered != allAnswered)):
            if not self.__RunAsThread:
                self.PeriodicHandle()

            for i in range(0, len(self.__listIPDev)):
                if (answered & (1 << i)) == 0:
                    ans = self.__GetMessageAnswer(sentCommandTag[i])
                    if (ans != None):
                        ansPacket = LDTP_Const.ldtp_byte_to_packet_ack(ans)
                        if (ansPacket.ErrorCode != 0):
                            print('StopDataAcquisition: Nack ' + str(ansPacket.ErrorCode))
                            error = True;
                        else:
                            answered += (1 << i)
            
            if (error == True):
                break;
            
            time.sleep(0.01)
            timeout = timeout - 1;

        self.__acqActive = False
        
        if (timeout == 0):
            print('StopDataAcquisition: Timeout')
            return False

        if (error == True):
            # already printed the error
            return False

        return True

    # ------------------------------------------------------------------
    def ExecuteFunction(self, devInd, start, funcNumber, args):

        if (devInd >= MAX_DEVICES) or (devInd < 0):
            print('ExecuteFunction: Invalid devInd')
            return (False, None)

        if (self.__listCommandSocket[devInd] == None):
            print('ExecuteFunction: Connection closed')
            return (False, None)
    
        if (start == True):
            packet = LDTP_Const.ldtp_create_packet_execfunc_start(funcNumber, args, self.__command_tag)
        else:
            packet = LDTP_Const.ldtp_create_packet_execfunc_stop(funcNumber, args, self.__command_tag)
        sentCommandTag = self.__command_tag
        self.__command_tag += 1

        self.__listCommandSocket[devInd].send(LDTP_Const.ldtp_packet_to_byte_execfunc(packet));

        argOut = []

        timeout = DEFAULT_TIMEOUT
        while (timeout > 0):
            if not self.__RunAsThread:
                self.PeriodicHandle()
            ans = self.__GetMessageAnswer(sentCommandTag)
            if (ans != None):
                ansPacket = LDTP_Const.ldtp_byte_to_packet_ack(ans)
                if (ansPacket.ErrorCode != 0):
                    print('ExecuteFunction: Nack ' + str(ansPacket.ErrorCode))
                    return (False, None)
                else:
                    aux = LDTP_Const.ldtp_get_specific_from_packet(ansPacket)
                    for i in range(2, len(aux)):
                        argOut.append(aux[i])
                    return (True, argOut)
            
            time.sleep(0.01)
            timeout = timeout - 1

        print('ExecuteFunction: Timeout')
        return (False, None)

    # ------------------------------------------------------------------
    def UpdateIDData(self, devInd):

        if (devInd >= MAX_DEVICES) or (devInd < 0):
            print('UpdateIDData: Invalid devInd')
            return False

        if (self.__listCommandSocket[devInd] == None):
            print('UpdateIDData: Connection closed')
            return False
    
        packet = LDTP_Const.ldtp_create_packet_idrequest(self.__command_tag)
        sentCommandTag = self.__command_tag
        self.__command_tag += 1

        self.__listCommandSocket[devInd].send(LDTP_Const.ldtp_packet_to_byte_idrequest(packet));

        timeout = DEFAULT_TIMEOUT
        while (timeout > 0):
            if not self.__RunAsThread:
                self.PeriodicHandle()
            ans = self.__GetMessageAnswer(sentCommandTag)
            if (ans != None):
                return True
            
            time.sleep(0.01)
            timeout = timeout - 1
            
        print('UpdateIDData: Timeout')
        return False

    # ------------------------------------------------------------------
    def UpdateStatus(self, devInd):

        if (devInd >= MAX_DEVICES) or (devInd < 0):
            print('UpdateStatus: Invalid devInd')
            return False

        if (self.__listCommandSocket[devInd] == None):
            print('UpdateStatus: Connection closed')
            return False
    
        packet = LDTP_Const.ldtp_create_packet_statusrequest(self.__command_tag)
        sentCommandTag = self.__command_tag
        self.__command_tag += 1

        self.__listCommandSocket[devInd].send(LDTP_Const.ldtp_packet_to_byte_statusrequest(packet));

        timeout = DEFAULT_TIMEOUT
        while (timeout > 0):
            if not self.__RunAsThread:
                self.PeriodicHandle()
            ans = self.__GetMessageAnswer(sentCommandTag)
            if (ans != None):
                return True
            
            time.sleep(0.01)
            timeout = timeout - 1
            
        print('UpdateStatus: Timeout')
        return False

    # ------------------------------------------------------------------
    def RequestParam(self, devInd, params):
        listParam = []

        if (devInd >= MAX_DEVICES) or (devInd < 0):
            print('RequestParam: Invalid devInd')
            return (False, None)

        if (self.__listCommandSocket[devInd] == None):
            print('RequestParam: Connection closed')
            return (False, None)
        
        for i in range(0, len(params)):
            listParam.append((params[i].ParamNum & 0x0000FFFF) + ((params[i].Size << 16) & 0x03FF0000))
            listParam.append((params[i].IndexI & 0x000001FF) + ((params[i].CountI << 9) & 0x0000FE00) +
                             ((params[i].IndexJ << 16) & 0x01FF0000) + ((params[i].CountJ << 25) & 0xFE000000))

        packet = LDTP_Const.ldtp_create_packet_requestparam(listParam, self.__command_tag)
        sentCommandTag = self.__command_tag
        self.__command_tag += 1

        self.__listCommandSocket[devInd].send(LDTP_Const.ldtp_packet_to_byte_requestparam(packet));

        timeout = DEFAULT_TIMEOUT
        while (timeout > 0):
            if not self.__RunAsThread:
                self.PeriodicHandle()
            ans = self.__GetMessageAnswer(sentCommandTag)
            if (ans != None):
                ansPacket = LDTP_Const.ldtp_byte_to_packet_paramdata(ans)
                
                if (ansPacket.ErrorCode != 0):
                    # only report the error
                    print('RequestParam: Nack ' + str(ansPacket.ErrorCode))

                params = self.__ExtractParamData(ansPacket.NumberParameters, ans)

                if (params != None):
                    return (True, params)
                else:
                    return (False, None)
                
            
            time.sleep(0.01)
            timeout = timeout - 1
            
        print('RequestParam: Timeout')
        return (False, None)

    # ------------------------------------------------------------------
    def __ExtractParamData(self, numParMsg, packet):

        if (numParMsg > 0):
            paramOut = []
            numParams = 0
                    
            paramdat = LDTP_Const.ldtp_get_paramdata_from_packet(packet)
            currPos = 0
            for i in range(0, numParMsg):
                paramOut.append(Param_Data())

                paramOut[numParams].ParamNum = ((paramdat[currPos] >> 0) & 0x0000FFFF)
                paramOut[numParams].Size = ((paramdat[currPos] >> 16) & 0x000003FF)
                paramOut[numParams].IndexI = ((paramdat[currPos + 1] >> 0) & 0x000001FF)
                paramOut[numParams].CountI = ((paramdat[currPos + 1] >> 9) & 0x0000007F)
                paramOut[numParams].IndexJ = ((paramdat[currPos + 1] >> 16) & 0x000001FF)
                paramOut[numParams].CountJ = ((paramdat[currPos + 1] >> 25) & 0x0000007F)
                currPos += 2
                for indI in range(paramOut[numParams].IndexI, paramOut[numParams].IndexI + paramOut[numParams].CountI):
                    for indJ in range(paramOut[numParams].IndexJ, paramOut[numParams].IndexJ + paramOut[numParams].CountJ):
                        for iSize in range(0, math.ceil(paramOut[numParams].Size / 4)):
                            if ((((iSize + 1) * 4) - paramOut[numParams].Size) == 3):
                                paramOut[numParams].Values.append(paramdat[currPos] & 0x000000FF)
                            elif ((((iSize + 1) * 4) - paramOut[numParams].Size) == 2):
                                paramOut[numParams].Values.append(paramdat[currPos] & 0x0000FFFF)
                            elif ((((iSize + 1) * 4) - paramOut[numParams].Size) == 1):
                                paramOut[numParams].Values.append(paramdat[currPos] & 0x00FFFFF)
                            else:
                                paramOut[numParams].Values.append(paramdat[currPos])
                            currPos += 1

            return paramOut
        
        else:
            return None

    # ------------------------------------------------------------------
    def SetParam(self, devInd, params):
        listParam = []

        if (devInd >= MAX_DEVICES) or (devInd < 0):
            print('SetParam: Invalid devInd')
            return False

        if (self.__listCommandSocket[devInd] == None):
            print('SetParam: Connection closed')
            return False
        
        for i in range(0, len(params)):
            listParam.append((params[i].ParamNum & 0x0000FFFF) + ((params[i].Size << 16) & 0x03FF0000))
            listParam.append((params[i].IndexI & 0x000001FF) + ((params[i].CountI << 9) & 0x0000FE00) +
                             ((params[i].IndexJ << 16) & 0x01FF0000) + ((params[i].CountJ << 25) & 0xFE000000))
            count = 0
            for indI in range(params[i].IndexI, params[i].IndexI + params[i].CountI):
                for indJ in range(params[i].IndexJ, params[i].IndexJ + params[i].CountJ):
                    listParam.append(params[i].Values[count])
                    count += 1

        packet = LDTP_Const.ldtp_create_packet_setparam(len(params), listParam, self.__command_tag)
        sentCommandTag = self.__command_tag
        self.__command_tag += 1

        self.__listCommandSocket[devInd].send(LDTP_Const.ldtp_packet_to_byte_setparam(packet));

        timeout = DEFAULT_TIMEOUT
        while (timeout > 0):
            if not self.__RunAsThread:
                self.PeriodicHandle()
            ans = self.__GetMessageAnswer(sentCommandTag)
            if (ans != None):
                ansPacket = LDTP_Const.ldtp_byte_to_packet_ack(ans)
                aux = LDTP_Const.ldtp_get_specific_from_packet(ans)
                
                if (ansPacket.ErrorCode != 0):
                    # only report the error
                    print('SetParam: Nack ' + str(ansPacket.ErrorCode) + '   ParamNum: ' + str((aux[0] >> 16) & 0x0000FFFF))
                    return False
                else:
                    return True
                
            
            time.sleep(0.01)
            timeout = timeout - 1
            
        print('SetParam: Timeout')
        return False


    # ------------------------------------------------------------------
    def __GetMessageAnswer(self, commandTag):
        for i in range (0, MAX_ANSWER_PACKETS):
            if (i < len(self.__listAnswer)):
                if (self.__listAnswer[i][4] == commandTag & 0xFF) and (self.__listAnswer[i][5] == ((commandTag >> 8) & 0x7F)):
                    return self.__listAnswer[i]
        return None
    
    # ------------------------------------------------------------------
    def SetSync(self, devInd, syncSource, forceBmc, useSyncOut, useAds2kCompat, stratum, timestampHigh, timestampLow):

        if (devInd >= MAX_DEVICES) or (devInd < 0):
            print('ExecuteFunction: Invalid devInd')
            return (False, None)

        if (self.__listCommandSocket[devInd] == None):
            print('ExecuteFunction: Connection closed')
            return (False, None)
    
        if (syncSource == LDTP_Const.LDTP_SYNC_EXT):
            syncSetup = 0
        elif (syncSource == LDTP_Const.LDTP_SYNC_GPS):
            syncSetup = 0x40
        elif (syncSource == LDTP_Const.LDTP_SYNC_PTP):
            syncSetup = 0x80
        else:
            syncSetup = 0xC0

        if (forceBmc):
            syncSetup = syncSetup | (0x10)

        if (useSyncOut):
            syncSetup = syncSetup | (0x20)
        
        if (useAds2kCompat):
            syncSetup = syncSetup | (0x01)


        packet = LDTP_Const.ldtp_create_packet_setsync(syncSetup, timestampHigh, timestampLow, stratum, self.__command_tag)

        sentCommandTag = self.__command_tag
        self.__command_tag += 1

        self.__listCommandSocket[devInd].send(LDTP_Const.ldtp_packet_to_byte_setsync(packet));

        timeout = DEFAULT_TIMEOUT
        while (timeout > 0):
            if not self.__RunAsThread:
                self.PeriodicHandle()
            ans = self.__GetMessageAnswer(sentCommandTag)
            if (ans != None):
                ansPacket = LDTP_Const.ldtp_byte_to_packet_ack(ans)
                if (ansPacket.ErrorCode != 0):
                    print('SetSync: Nack ' + str(ansPacket.ErrorCode))
                    return False
                else:
                    return True
            
            time.sleep(0.01)
            timeout = timeout - 1

        print('SetSync: Timeout')
        return False

    # ------------------------------------------------------------------
    def PeriodicHandle(self):
    
        for i in range(0, len(self.__listIPDev)):
            if (self.__listCommandSocket[i] != None):
                while (True):
                    try:
                        packet = self.__listCommandSocket[i].recv(1600)
                    except socket.timeout as err:
                        break
                    except socket.error as err:
                        break
                    else:
                        if (len(packet) < 20):
                            continue
                        
                        self.__HandleAnswer(i, packet)
                        
                        if (len(self.__listAnswer) < MAX_ANSWER_PACKETS):
                            self.__listAnswer.append(packet)
                        else:
                            self.__listAnswer[self.__ansPos] = packet
                        self.__ansPos += 1
                        if (self.__ansPos >= MAX_ANSWER_PACKETS):
                            self.__ansPos = 0

            if (self.__listDataSocket[i] != None):
                while (True):
                    try:
                        packet = self.__listDataSocket[i].recv(1600)
                    except socket.timeout as err:
                        break
                    except socket.error as err:
                        break
                    else:
                        if (len(packet) < 20):
                            continue

                        pac = LDTP_Const.ldtp_byte_to_packet_generic(packet)

                        if (pac.PacketCode == LDTP_Const.LDTP_MSG_PACKCODE_DATAPACKET):
                            self.__HandleDataPacket(i, packet)
                        else:
                            self.__HandleAnswer(i, packet)
                            
                            if (len(self.__listAnswer) < MAX_ANSWER_PACKETS):
                                self.__listAnswer.append(packet)
                            else:
                                self.__listAnswer[self.__ansPos] = packet
                            self.__ansPos += 1
                            if (self.__ansPos >= MAX_ANSWER_PACKETS):
                                self.__ansPos = 0

                if (datetime.datetime.now() - self.__listDev[i].LastKeepAlive).seconds > 15:
                    self.SendKeepAlive(i)

        self.__SyncSamples()
    
    # ------------------------------------------------------------------
    def UpdateStatusAll(self):
        answered = 0
        sentCommandTag = []
        
        allAnswered = 0
        for i in range(0, len(self.__listIPDev)):
            allAnswered += (1 << i)
        
        for i in range(0, len(self.__listIPDev)):
            if (self.__listCommandSocket[i] != None):
                packet = LDTP_Const.ldtp_create_packet_statusrequest(self.__command_tag)
                sentCommandTag.append(self.__command_tag)
                self.__command_tag += 1

                self.__listCommandSocket[i].send(LDTP_Const.ldtp_packet_to_byte_statusrequest(packet));
            else:
                sentCommandTag.append(0)
                answered = answered + (1 << i)

        timeout = DEFAULT_TIMEOUT
        while ((timeout > 0) and (answered != allAnswered)):
            if not self.__RunAsThread:
                self.PeriodicHandle()

            for i in range(0, len(self.__listIPDev)):
                if (answered & (1 << i)) == 0:
                    ans = self.__GetMessageAnswer(sentCommandTag[i])
                    if (ans != None):
                        answered += (1 << i)
            
            time.sleep(0.01)
            timeout = timeout - 1;

        if (timeout == 0):
            print('StopDataAcquisition: Timeout')
            return False

        return True

    # ------------------------------------------------------------------
    def SendKeepAlive(self, devInd):
        
        if (devInd >= MAX_DEVICES) or (devInd < 0):
            print('SendKeepAlive: Invalid devInd')
            return False

        if (self.__listDataSocket[devInd] == None):
            print('SendKeepAlive: Connection closed')
            return False

        packet = LDTP_Const.ldtp_create_packet_keepalive(self.__listDev[devInd].ConnectionKey, self.__command_tag)
        sentCommandTag = self.__command_tag
        self.__command_tag += 1

        self.__listDataSocket[devInd].send(LDTP_Const.ldtp_packet_to_byte_keepalive(packet));
        
        self.__listDev[devInd].LastKeepAlive = datetime.datetime.now()

        return True

    # ------------------------------------------------------------------
    def __UpdateDevStatus(self, devInd, status):
        
        if (devInd >= MAX_DEVICES) or (devInd < 0):
            print('__UpdateDevStatus: Invalid devInd')
            return False

        self.__listDev[devInd].Status = status
        if ((status & 0x2000) != 0):
            self.__listDev[devInd].Synced = True
        else:
            self.__listDev[devInd].Synced = False
            
        self.__listDev[devInd].SystemState = ((status >> 14) & 0x0003)

        return True

    # ------------------------------------------------------------------
    def __HandleAnswer(self, devInd, packet):
        
        if (devInd >= MAX_DEVICES) or (devInd < 0):
            print('__HandleAnswer: Invalid devInd')
            return False

        packAux = LDTP_Const.ldtp_byte_to_packet_generic(packet)

        if packAux.PacketCode == LDTP_Const.LDTP_MSG_PACKCODE_ACK:
            packAck = LDTP_Const.ldtp_byte_to_packet_ack(packet)
            self.__UpdateDevStatus(devInd, packAck.SystemStatus)
            return True

        if packAux.PacketCode == LDTP_Const.LDTP_MSG_PACKCODE_STATUSDATA:
            packStatus = LDTP_Const.ldtp_byte_to_packet_statusdata(packet)
            self.__UpdateDevStatus(devInd, packStatus.SystemStatus)
            self.__listDev[devInd].Timestamp = packStatus.TimestampS
            self.__sampFreq = packStatus.SampleFreq
            return True

        if packAux.PacketCode == LDTP_Const.LDTP_MSG_PACKCODE_IDDATA:
            packIDData = LDTP_Const.ldtp_byte_to_packet_iddata(packet)
            self.__UpdateDevStatus(devInd, packIDData.SystemStatus)
            self.__listDev[devInd].Timestamp = packIDData.Timestamp

            self.__listDev[devInd].NumAnInCh = packIDData.NumAnInCh
            self.__listDev[devInd].NumPulseCh = packIDData.NumPulseCh
            self.__listDev[devInd].NumDigInCh = packIDData.NumDigInCh
            self.__listDev[devInd].NumNavCh = packIDData.NumNavCh
            self.__listDev[devInd].NumCalcCh = packIDData.NumCalcCh
            self.__listDev[devInd].NumAnOutCh = packIDData.NumAnOutCh
            self.__listDev[devInd].NumDigOutCh = packIDData.NumDigOutCh
            self.__listDev[devInd].NumIntCh = packIDData.NumIntCh
            self.__listDev[devInd].NumExtAnCh = packIDData.NumExtAnCh
            self.__listDev[devInd].NumExtDigCh = packIDData.NumExtDigCh

            return True


    # ------------------------------------------------------------------
    def __HandleDataPacket(self, devInd, packet):
        chInd = 0

        if (devInd >= MAX_DEVICES) or (devInd < 0):
            print('__HandleDataPacket: Invalid devInd')
            return False

        for i in range (0, devInd):
            if (i < len(self.__listDataSocket)):
                if (self.__listDataSocket[i] != None):
                    chInd += self.__acqNumCh[i]

        packAux = LDTP_Const.ldtp_byte_to_packet_data(packet)
        samples = LDTP_Const.ldtp_get_samples_from_packet(packet)

        self.__listDev[devInd].Timestamp = packAux.TimestampS
        self.__sampFreq = packAux.SampleFreq
        self.__UpdateDevStatus(devInd, packAux.SystemStatus)

        timeIncrement = 1.0 / packAux.SampleFreq
        sampTime = packAux.TimestampS + (packAux.TimestampSs / 4294967296.0)
        if (self.__startTimestamp == 0):
            self.__startTimestamp = packAux.TimestampS
        if (self.UseAbsoluteTimestamp == False):
            sampTime -= self.__startTimestamp

        if (packAux.FrameNumber < self.__acqLastFrame[devInd]):
            if ((self.__acqLastFrame[devInd] - packAux.FrameNumber) > 99999):
                # it is likely that the framenumber returned to 0 after reaching 0xFFFFFFFF
                missingFrames = 0xFFFFFFFF - (self.__acqLastFrame[devInd] - packAux.FrameNumber)
            else:
                #maybe an old packet, it will be ignored
                return True
        else:
            missingFrames = packAux.FrameNumber - self.__acqLastFrame[devInd] - 1;

        # fill the buffer with the missing samples
        if ((missingFrames * packAux.SamplesPerChannel) >= SAMP_BUFF_SIZE):
            # if lost the entire buffer, just update the sampCount and sampPos
            self.__sampCount[devInd] += missingFrames * packAux.SamplesPerChannel
            self.__sampPos[devInd] = 0
        else:
            for i in range (0, missingFrames):
                for iSamp in range(0, packAux.SamplesPerChannel):
                    if (self.__sampPos[devInd] == 0):
                        for iCh in range(0, self.__acqNumCh[devInd]):
                            self.__samples[chInd + iCh][self.__sampPos[devInd]] = self.__samples[chInd + iCh][SAMP_BUFF_SIZE - 1]
                    else:
                        for iCh in range(0, self.__acqNumCh[devInd]):
                            self.__samples[chInd + iCh][self.__sampPos[devInd]] = self.__samples[chInd + iCh][self.__sampPos[devInd]-1]

                    self.__sampPos[devInd] += 1
                    if (self.__sampPos[devInd] >= SAMP_BUFF_SIZE):
                        self.__sampPos[devInd] = 0
                    self.__sampCount[devInd] += 1
        
        if (missingFrames > 0):
            self.__sampsLost[devInd] += missingFrames * packAux.SamplesPerChannel

        # new samples
        for iSamp in range(0, packAux.SamplesPerChannel):
            for iCh in range(0, packAux.TotalChNumber):
                self.__samples[chInd + iCh][self.__sampPos[devInd]] = samples[(iSamp * packAux.TotalChNumber) + iCh]
                #print('iSamp = ' + str(iSamp) + '  iCh = ' + str(iCh))
            self.__sampleTime[self.__sampPos[devInd]] = sampTime
            sampTime += timeIncrement
            self.__sampPos[devInd] += 1
            if (self.__sampPos[devInd] >= SAMP_BUFF_SIZE):
                self.__sampPos[devInd] = 0
            self.__sampCount[devInd] += 1

        self.__acqLastFrame[devInd] = packAux.FrameNumber

        return True

    # ------------------------------------------------------------------
    def __SyncSamples(self):
        latestSamp = 0
        indexLatest = 0

        if (self.__acqActive == False):
            return True

        for iDev in range(0, len(self.__listIPDev)):
            if (self.__listDataSocket[iDev] != None):
                if (self.__sampCount[iDev] > latestSamp):
                    latestSamp = self.__sampCount[iDev];
                    indexLatest = iDev

        if (latestSamp == 0):
            return True

        # now, we must allign devices that are too far behind
        chInd = 0
        for iDev in range(0, len(self.__listIPDev)):
            if (self.__listDataSocket[iDev] != None):
                if ((latestSamp - self.__sampCount[iDev]) >= SAMP_BUFF_SIZE):
                    # lost the entire buffer! just update the sampCount and sampPos
                    self.__sampsLost[devInd] += latestSamp - self.__sampCount[iDev]
                    self.__sampCount[iDev] = latestSamp
                    self.__sampPos[iDev] = 0
                elif ((latestSamp - self.__sampCount[iDev]) > (self.__sampFreq * 2.5)):
                    for iSamp in range(0, (latestSamp - self.__sampCount[iDev])):
                        if (self.__sampPos[iDev] == 0):
                            for iCh in range(0, self.__acqNumCh[iDev]):
                                self.__samples[chInd + iCh][self.__sampPos[iDev]] = self.__samples[chInd + iCh][SAMP_BUFF_SIZE - 1]
                        else:
                            for iCh in range(0, self.__acqNumCh[devInd]):
                                self.__samples[chInd + iCh][self.__sampPos[iDev]] = self.__samples[chInd + iCh][self.__sampPos[iDev]-1]

                        self.__sampPos[iDev] += 1
                        if (self.__sampPos[iDev] >= SAMP_BUFF_SIZE):
                            self.__sampPos[iDev] = 0
                            
                    self.__sampsLost[devInd] += latestSamp - self.__sampCount[iDev]       
                    self.__sampCount[iDev] = (latestSamp)
                    
            chInd += self.__acqNumCh[iDev]

        # now check the most delayed
        indexDelay = 0
        for iDev in range(0, len(self.__listIPDev)):
            if (self.__listDataSocket[iDev] != None):
                if (self.__sampCount[iDev] < latestSamp):
                    latestSamp = self.__sampCount[iDev];
                    indexDelay = iDev

        self.__syncSampCount = latestSamp
        self.__syncSampPos = self.__sampPos[indexDelay]

        return True

    # ------------------------------------------------------------------
    def GetSamples(self, ch, numSamps):
        # ch = -1 reads the timestamp vector

        lastSamp = self.__syncSampCount

        if numSamps > self.__syncSampCount:
            numSamps = self.__syncSampCount

        sampStart = lastSamp

        samples = numpy.zeros(numSamps)
        start = ((lastSamp - numSamps) % SAMP_BUFF_SIZE)
        end = start + numSamps
        if end >= SAMP_BUFF_SIZE:
            end = end % SAMP_BUFF_SIZE
            for i in range(start, SAMP_BUFF_SIZE):
                if (ch < 0):
                    samples[i - start] = self.__sampleTime[i]
                else:
                    samples[i - start] = self.__samples[ch][i]
            for i in range(0, end):
                if (ch < 0):
                    samples[i + (SAMP_BUFF_SIZE - start)] = self.__sampleTime[i]
                else:
                    samples[i + (SAMP_BUFF_SIZE - start)] = self.__samples[ch][i]
        else:
            for i in range(start, end):
                if (ch < 0):
                    samples[i - start] = self.__sampleTime[i]
                else:
                    samples[i - start] = self.__samples[ch][i]

        return samples

    # ------------------------------------------------------------------
    def GetNumSamps(self):
        return self.__syncSampCount

    # ------------------------------------------------------------------
    def GetSampsLost(self, devInd):
        if (len(self.__sampsLost) > devInd):
            return self.__sampsLost[devInd]
        else:
            return 0

    # ------------------------------------------------------------------
    def GetDevInfo(self, devInd):
        if (devInd >= MAX_DEVICES) or (devInd < 0):
            print('GetDevInfo: Invalid devInd')
            return False

        return self.__listDev[devInd]

