import LDTP_Const
import LDTP_Module
import socket
import time
import numpy
import struct
import math

# ------------------------------------------------------------------
class LynxDriverV1:
    """ LynxDriverV1

    This class is used for data acquisition of devices from Lynx
    Tecnologia, compatible with the LDTP communication protocol
    (ex: ADS1800, ADS2500, etc).
    Obs: ADS1000 and ADS2000 are not compatible with this driver.
    
    Up to 8 devices can be connected at the same time. Data from
    all of them will be synchronous (if the devices were configured
    correctly).

    Usage:
    1- Connect to the device using ConnectTo()
    2- Start acquisition using StartAcq()
    3- Keep calling GetAllSamples() perodically to retrieve data
       (recommended faster than 100ms)
    4- Stop acquistition using StopAcq()
    5- Disconnect from the device using DisconnectFrom()

    Important:
    All synchronism and channel configuration must be programmed
    using the device assistant (ex: ADS1800Assistant, ADS2500Assistant,
    etc). These assistants can be called using the Lynx@Net program,
    provided with the device, for Windows.
    The configuration is stored in the devices, so you may program
    the device on a Windows machine and run the acquisition using
    this class.
    """
    
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    def __init__(self):
        self.Module = LDTP_Module.LDTPModule()

        self.__listIp = []

        self.__chRef = []
        self.__lastSampRead = []
        self.__lastSampTimeRead = 0
        self.__lastSampReadAll = 0

        self.__sampFreqOpt = []
        self.__sampFreqNumOpt = []

        self.ChInfo = []

        self.__useTimestamp = 0

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------




    # ------------------------------------------------------------------
    def ConnectTo(self, devIp):
        """Connects to a device with the provided IP

        This function tries to connect to the device with the provided
        IP. The local IP address is automatically chosen. If there is
        more than one interface that can reach the device at the same
        time(ex: WiFi and Ethernet), it is recommended to disconenct
        one of the interfaces.
        After openning the connection, the function retrieves the
        channel name, unit and scale limits of all channels.

        Obs:
        If this funcion fails, try pinging the IP address. If there
        is no answer, check the IP address. If you are certain of the
        address, it is possible that a route is missing. On Linux,
        check the command line "ip route add" or "route add". On
        Windows, check the command line "route add"

        Parameters
        ----------
        devIp : str
            IP address of the device. Example format: '192.168.1.1'

        Return
        ------
            False : An error occurred connecting or reading data from
                    the device
            True : Successfully connected and read data from the device
        """

        # -------------------
        def __GetLocalIp():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect((devIp, 1))
                IP = s.getsockname()[0]
            except Exception:
                IP = '127.0.0.1'
            finally:
                s.close()
            return IP
        # -------------------
        
        
        for i in range(0, len(self.__listIp)):
            if (devIp == self.__listIp[i]):
                print('ConnectTo: Already connected to this IP')
                return False

        indDev = len(self.__listIp)
        for i in range(0, len(self.__listIp)):
            if self.__listIp[i] == '':
                indDev = i
                break;

        if indDev >= LDTP_Module.MAX_DEVICES:
            print('ConnectTo: Max devices reached')
            return False

        if self.Module.OpenConnection(indDev, devIp, __GetLocalIp()):
            if self.Module.UpdateIDData(indDev):
                if (len(self.ChInfo) <= indDev):
                    self.ChInfo.append([])
                else:
                    self.ChInfo[indDev] = []

                if (self.__GetSampFreqOpt(indDev) == False):
                    print('ConnectTo: Error reading available sample frequencies')
                    return False
                    
                if (self.__GetAnChannelConf(indDev, LDTP_Const.LDTP_CHTYPE_ANIN) == False):
                    print('ConnectTo: Error reading AnIn channel conf')
                    return False
                if (self.Module.GetDevInfo(indDev).NumPulseCh > 0):
                    if (self.__GetAnChannelConf(indDev, LDTP_Const.LDTP_CHTYPE_PULSE) == False):
                        print('ConnectTo: Error reading Pulse channel conf')
                        return False
                if (self.Module.GetDevInfo(indDev).NumDigInCh > 0):
                    if (self.__GetDigChannelConf(indDev, LDTP_Const.LDTP_CHTYPE_DIGIN) == False):
                        print('ConnectTo: Error reading DigIn channel conf')
                        return False
                if (self.Module.GetDevInfo(indDev).NumNavCh > 0):
                    if (self.__GetAnChannelConf(indDev, LDTP_Const.LDTP_CHTYPE_NAV) == False):
                        print('ConnectTo: Error reading Nav channel conf')
                        return False
                if (self.Module.GetDevInfo(indDev).NumAnOutCh > 0):
                    if (self.__GetAnChannelConf(indDev, LDTP_Const.LDTP_CHTYPE_ANOUT) == False):
                        print('ConnectTo: Error reading AnOut channel conf')
                        return False
                if (self.Module.GetDevInfo(indDev).NumDigOutCh > 0):
                    if (self.__GetDigChannelConf(indDev, LDTP_Const.LDTP_CHTYPE_DIGOUT) == False):
                        print('ConnectTo: Error reading DigOut channel conf')
                        return False
                if (self.Module.GetDevInfo(indDev).NumIntCh > 0):
                    if (self.__GetAnChannelConf(indDev, LDTP_Const.LDTP_CHTYPE_INTERN) == False):
                        print('ConnectTo: Error reading Int channel conf')
                        return False
                if (self.Module.GetDevInfo(indDev).NumExtAnCh > 0):
                    if (self.__GetAnChannelConf(indDev, LDTP_Const.LDTP_CHTYPE_EXTAN) == False):
                        print('ConnectTo: Error reading ExtAn channel conf')
                        return False
                if (self.Module.GetDevInfo(indDev).NumExtDigCh > 0):
                    if (self.__GetDigChannelConf(indDev, LDTP_Const.LDTP_CHTYPE_EXTDIG) == False):
                        print('ConnectTo: Error reading ExtDig channel conf')
                        return False
                while (len(self.__listIp) <= indDev):
                    self.__listIp.append('')
                self.__listIp[indDev] = devIp
                return True
            else:
                print('ConnectTo: Error updating IDData')
                return False
        else:
            print('ConnectTo: Error on OpenConnection')
            return False

    # ------------------------------------------------------------------
    def DisconnectFrom(self, devIp):
        """Disconnects from the device with the provided IP

        This function disconnects from the device with the provided
        IP. If there is an active data connection, it will be released.

        Parameters
        ----------
        devIp : str
            IP address of the device. Example format: '192.168.1.1'

        Return
        ------
            False : No device with the provided IP address was
                    previously connected.
            True : Successfully disconnected from the device
        """
        
        for i in range(0, len(self.__listIp)):
            if (devIp == self.__listIp[i]):
                if (self.Module.DataConnActive[i]):
                    self.Module.ReleaseDataConnection(i)
                self.Module.CloseConnection(i)
                self.__listIp[i] = ''
                return True
        print('DisconnectFrom: Device not found: ' + str(devIp))
        return False

    # ------------------------------------------------------------------
    def StartAcq(self, sampFreq, channels, useDeviceTimestamp = False):
        """Configures and start acquisition on all devices

        This function programs the data acquisition on each device
        and starts the acquisition synchronously on all devices.

        Parameters
        ----------
        sampFreq : float32 or integer
            Desired sample frequency. The available options can be
            retrieved using the function GetAvailableSampFreq()
            
        channels: set of set of [string, integer, integer]
            A set of channels that will be acquired. Each position of
            this set is another set with 3 items:

            [deviceIP: string, channelType: int, channelNumber: int]
            
            The deviceIP is used to identify the device.
            
            The channelType indicates the channel type (analog input,
            pulse channel, etc). The options are available on file
            LDPT_Const.
            Ex: LDTP_Const.LDTP_CHTYPE_ANIN for analog input,
            LDTP_Const.LDTP_CHTYPE_PULSE for pulse channels, etc

            The channelNumber is the index of the channel, starting
            from 0. Ex: the first analog channel of a device has a
            channelNumber = 0. The eighth, has a channelNumber = 7.

        useDeviceTimestamp: boolean
            If true, the timestamp channel will be in UTC, according
            to the device clock.
            If false, the timestamp channel will start at 0 when the 
            data acquisition begins.

        Return
        ------
            False : The function will print the specific error if it
                    fails.
            True : Successfully programmed and started the acquisition.
        """
        
        def __ReleaseAll():
            for iDev in range(0, len(self.__listIp)):
                if (self.Module.DataConnActive[iDev]):
                    self.Module.ReleaseDataConnection(iDev)
            return True
                    

        listCh = []

        # create lists of channels for each device
        for iCh in range(0, len(channels)):

            if (channels[iCh][0] == ''):
                print('StartAcq: invalid device IP on channel ' + str(iCh))
                return False
            
            devInd = -1
            for i in range(0, len(self.__listIp)):
                if (channels[iCh][0] == self.__listIp[i]):
                    devInd = i
                    break;
            if ((devInd < 0)):
                print('StartAcq: Device not found IP: ' + str(channels[iCh][0]) + '  on channel' + str(iCh))
                return False

            while (len(listCh) <= devInd):
                listCh.append([])

            listCh[devInd].append((channels[iCh][1] << 10) + (channels[iCh][2] & 0x03FF))

        # now configure each device
        self.__chRef = []
        self.__lastSampRead = []
        for iDev in range(0, len(self.__listIp)):
            if iDev < len(listCh):
                if (len(listCh[iDev]) > 0):
                    if (self.Module.RequestDataConnection(iDev) == False):
                        print('StartAcq: Error requesting data connection to ' + str(self.__listIp[iDev]))
                        __ReleaseAll()
                        return False

                    # update reference list
                    for iCh in range(0, len(listCh[iDev])):
                        found = False
                        for iDevCh in range(0, len(self.ChInfo[iDev])):
                            if (listCh[iDev][iCh] == self.ChInfo[iDev][iDevCh].ChIndex):
                                self.__chRef.append(iDevCh + (iDev << 16))
                                self.__lastSampRead.append(0)
                                found = True
                                break
                        if (found == False):
                            __ReleaseAll()
                            devIp = self.__listIp[iDev]
                            chType = ((listCh[iDev][iCh] >> 16) & 0x00FF)
                            chNum = ((listCh[iDev][iCh]) & 0x0000FFFF)                            
                            print('StartAcq: Channel not found: dev ' + str(devIp) + '  chType ' + str(chType) + '  chNum ' + str(chNum))
                            return False

                    # configure acquisition
                    if (self.Module.DataAcqSetup(iDev, sampFreq, listCh[iDev]) == False):
                        print('StartAcq: Error configuring acquisition on ' + str(self.__listIp[iDev]))
                        __ReleaseAll()
                        return False
                    
        self.__useTimestamp = useDeviceTimestamp
        self.Module.UseAbsoluteTimestamp = self.__useTimestamp;

        # ready to start
        if (self.Module.StartDataAcquisition() == False):
            print('StartAcq: Error starting acquisition')
            __ReleaseAll()
            return False
        
        self.__lastSampTimeRead = 0
        self.__lastSampReadAll = 0

        return True

    # ------------------------------------------------------------------
    def StopAcq(self):
        """Stop current acquisition on all devices

        This function stop the acquisition on all connected devices.

        Parameters
        ----------
        None

        Return
        ------
            False : The function will print the specific error if it
                    fails.
            True : Successfully stopped the acquisition.
        """
        
        success = self.Module.StopDataAcquisition()
        for iDev in range(0, len(self.__listIp)):
            if self.Module.DataConnActive[iDev]:
                success = self.Module.ReleaseDataConnection(iDev) and success
        return success

    # ------------------------------------------------------------------
    def GetSamples(self, channel):
        """Retrieve the samples from the channel
          Depracated - use GetAllSamples

        This function retrieve samples from the channel, starting
        one sample after the last sample read on that channel, up
        to the latest sample received.
        This function also calls the funcion PeriodicHandle() to
        retrieve sample packets from the network buffer.

        Parameters
        ----------            
        channel: integer
            Index of the channel, according to the list of channels
            used on StartAcq(). Example: a channel == 0 will return
            the samples of the first channel of the list passed to
            StartAcq().
            A value of -1 can be used to read the timestamp vector

        Return
        ------
            Set of double, with the samples read from the channel.
            Returns an empty set if there is an error, or if no new
            samples were received since the last time this function
            was called.
        """

        self.PeriodicHandle()
        
        if (channel < -1) or (channel >= len(self.__chRef)):
            print('GetSamples: Invalid channel')
            return []

        if (channel < 0):
            sampsToRead = self.Module.GetNumSamps() - self.__lastSampTimeRead
        else:
            sampsToRead = self.Module.GetNumSamps() - self.__lastSampRead[channel]

        if (sampsToRead > 0):
            if (channel < 0):
                rawSamp = self.Module.GetSamples(channel, sampsToRead)
                sampsEng = []
                for i in range(0, sampsToRead):
                    sampsEng.append(rawSamp[i])

                self.__lastSampTimeRead += sampsToRead
                return sampsEng
            
            else:
                devInd = ((self.__chRef[channel] >> 16) & 0x00FF)
                chInd = ((self.__chRef[channel]) & 0xFFFF)

                rawSamp = self.Module.GetSamples(channel, sampsToRead)
                sampsEng = []
                for i in range(0, sampsToRead):
                    sampsEng.append(rawSamp[i] * self.ChInfo[devInd][chInd].coefAng + self.ChInfo[devInd][chInd].coefLin)

                self.__lastSampRead[channel] += sampsToRead
                return sampsEng
        
        else:
            return []
        
    # ------------------------------------------------------------------
    def GetAllSamples(self):
        """Retrieve samples from all channels

        This function retrieve all available samples from all channel, starting
        one sample after the last sample read on that channel, up
        to the latest sample received. The first channel is the timestamp of each
        sample. The other channels follow the order of the list of channels
        used on StartAcq(). The samples of the channels are scaled according
        to the High and Low Limits of the channel.

        Parameters
        ----------

        Return
        ------
            Set of sets of double, with the samples read.
            Returns an empty set if there is an error, or if no new
            samples were received since the last time this function
            was called.
        """

        self.PeriodicHandle()

        sampsToRead = self.Module.GetNumSamps() - self.__lastSampReadAll

        result = []

        if (sampsToRead > 0):
            sampsEng = self.Module.GetSamples(-1, sampsToRead)
            result.append(sampsEng)
            
            for iCh in range(0, len(self.__chRef)):
                devInd = ((self.__chRef[iCh] >> 16) & 0x00FF)
                chInd = ((self.__chRef[iCh]) & 0xFFFF)

                rawSamp = self.Module.GetSamples(iCh, sampsToRead)
                sampsEng = []
                for i in range(0, sampsToRead):
                    sampsEng.append(rawSamp[i] * self.ChInfo[devInd][chInd].coefAng + self.ChInfo[devInd][chInd].coefLin)
                result.append(sampsEng)

            self.__lastSampReadAll += sampsToRead
            return result
        
        else:
            return []
        
    # ------------------------------------------------------------------
    def GetAllSamplesRaw(self):
        """Retrieve raw samples from all channels

        This function retrieve all available samples from all channel, starting
        one sample after the last sample read on that channel, up
        to the latest sample received. The first channel is the timestamp of each
        sample. The other channels follow the order of the list of channels
        used on StartAcq(). The samples are in raw format (32 bit integer).

        Parameters
        ----------

        Return
        ------
            Set of sets of double, with the samples read.
            Returns an empty set if there is an error, or if no new
            samples were received since the last time this function
            was called.
        """

        self.PeriodicHandle()

        sampsToRead = self.Module.GetNumSamps() - self.__lastSampReadAll

        result = []

        if (sampsToRead > 0):
            sampsEng = self.Module.GetSamples(-1, sampsToRead)
            result.append(sampsEng)
            
            for iCh in range(0, len(self.__chRef)):
                devInd = ((self.__chRef[iCh] >> 16) & 0x00FF)
                chInd = ((self.__chRef[iCh]) & 0xFFFF)

                rawSamp = self.Module.GetSamples(iCh, sampsToRead)
                sampsEng = []
                for i in range(0, sampsToRead):
                    sampsEng.append(int(rawSamp[i]))
                result.append(sampsEng)

            self.__lastSampReadAll += sampsToRead
            return result
        
        else:
            return []

    # ------------------------------------------------------------------
    def PeriodicHandle(self):
        """Handles the reception of messages from the devices

        This function retrieves message packets from the network
        buffer. During data acquisition, must be called periodically
        (< 100ms) to avoid losing samples.
        The function GetSamples() also calls this function, so if
        the GetSamples() is called periodically, it is not necessary
        to call this function.

        Parameters
        ----------            
        None

        Return
        ------
        Nothing
        """
        
        self.Module.PeriodicHandle()

    # ------------------------------------------------------------------
    def GetSamplesLost(self, channel):
        """Return the number of samples lost so far

        This function retrieves the number of samples lost since the
        acquisition started. The reasons for losing samples are:
        -GetSamples() or PeriodicHandle() were not executed for too
         long.
        -Packets from the device were lost in the network, usually
         because the network is suffering heavy traffic.

        Parameters
        ----------            
        channel: integer
            Index of the channel, according to the list of channels
            used on StartAcq(). Example: a channel == 0 will return
            the samples of the first channel of the list passed to
            StartAcq().
            
        Return
        ------
            Number of samples lost on the channel.
        """
        
        if (channel < 0) or (channel >= len(self.__chRef)):
            print('GetSamplesLost: Invalid channel')
            return 0
        
        devInd = ((self.__chRef[channel] >> 16) & 0x00FF)
        return self.Module.GetSampsLost(devInd)

    # ------------------------------------------------------------------
    def GetAvailableSampFreq(self):
        """Return the possible sample frequencies

        This function returns the sample frequencies available for
        acquisition with the currently connected devices.
        If different devices (with different sample frequencies) are
        connected, only the frequencies available in all devices can
        be used.

        Parameters
        ----------            
        None
            
        Return
        ------
            Set of double with the available sample frequencies.
        """
        
        freqAv = []
        if (len(self.__listIp) < 1):
            return 0
        if (self.__listIp == ''):
            return 0
        
        for i in range(0, self.__sampFreqNumOpt[0]):
            freqOk = True
            # checks if this frequency exists on other devices
            for iDev in range(1, len(self.__listIp)):
                if (self.__listIp != ''):
                    found = False
                    for j in range(0, self.__sampFreqNumOpt[iDev]):
                        if (self.__sampFreqOpt[0][i] == self.__sampFreqOpt[iDev][j]):
                            found = True
                            break
                    if (found == False):
                        freqOk = False
                        break
            if (freqOk):
                freqAv.append(self.__sampFreqOpt[0][i])

        return freqAv


    # ------------------------------------------------------------------
    def __GetAnChannelConf(self, devInd, chType):

        if (chType == LDTP_Const.LDTP_CHTYPE_ANIN):
            numCh = self.Module.GetDevInfo(devInd).NumAnInCh
        elif (chType == LDTP_Const.LDTP_CHTYPE_PULSE):
            numCh = self.Module.GetDevInfo(devInd).NumPulseCh
        elif (chType == LDTP_Const.LDTP_CHTYPE_NAV):
            numCh = self.Module.GetDevInfo(devInd).NumNavCh
        elif (chType == LDTP_Const.LDTP_CHTYPE_CALC):
            numCh = self.Module.GetDevInfo(devInd).NumCalcCh
        elif (chType == LDTP_Const.LDTP_CHTYPE_ANOUT):
            numCh = self.Module.GetDevInfo(devInd).NumAnOutCh
        elif (chType == LDTP_Const.LDTP_CHTYPE_INTERN):
            numCh = self.Module.GetDevInfo(devInd).NumIntCh
        elif (chType == LDTP_Const.LDTP_CHTYPE_EXTAN):
            numCh = self.Module.GetDevInfo(devInd).NumExtAnCh
        else:
            print('__GetAnChannelConf: Invalid ChType')
            return False

        chOffset = len(self.ChInfo[devInd])

        # Channel name
        aux = []
        aux.append(LDTP_Module.Param_Data())
        
        if (chType == LDTP_Const.LDTP_CHTYPE_ANIN):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_ANIN_CHNAME
        elif (chType == LDTP_Const.LDTP_CHTYPE_PULSE):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_PULSE_CHNAME
        elif (chType == LDTP_Const.LDTP_CHTYPE_NAV):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_NAV_CHNAME
        elif (chType == LDTP_Const.LDTP_CHTYPE_CALC):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_CALC_CHNAME
        elif (chType == LDTP_Const.LDTP_CHTYPE_ANOUT):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_ANOUT_CHNAME
        elif (chType == LDTP_Const.LDTP_CHTYPE_INTERN):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_INT_CHNAME
        elif (chType == LDTP_Const.LDTP_CHTYPE_EXTAN):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_EXTAN_CHNAME
        
        aux[0].Size = 32
        aux[0].IndexI = 0
        aux[0].CountI = numCh
        aux[0].IndexJ = 0
        aux[0].CountJ = 1

        res = self.Module.RequestParam(devInd, aux);
        if (res[0] == False):
            return False
        else:
            count = 0
            auxVal = []
            for i in range(0, math.ceil(res[1][0].Size / 4)):
                auxVal.append(0)
            for i in range(0, aux[0].CountI):
                self.ChInfo[devInd].append(LDTP_Module.ChInfo())
                for j in range(0, math.ceil(res[1][0].Size / 4)):
                    auxVal[j] = res[1][0].Values[count]
                    count += 1
                self.ChInfo[devInd][i + chOffset].Name = self.__IntToStr(auxVal)

        # Channel Unit
        if (chType == LDTP_Const.LDTP_CHTYPE_ANIN):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_ANIN_UNIT
        elif (chType == LDTP_Const.LDTP_CHTYPE_PULSE):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_PULSE_UNIT
        elif (chType == LDTP_Const.LDTP_CHTYPE_NAV):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_NAV_UNIT
        elif (chType == LDTP_Const.LDTP_CHTYPE_CALC):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_CALC_UNIT
        elif (chType == LDTP_Const.LDTP_CHTYPE_ANOUT):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_ANOUT_UNIT
        elif (chType == LDTP_Const.LDTP_CHTYPE_INTERN):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_INT_UNIT
        elif (chType == LDTP_Const.LDTP_CHTYPE_EXTAN):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_EXTAN_UNIT
            
        aux[0].Size = 32
        aux[0].IndexI = 0
        aux[0].CountI = numCh
        aux[0].IndexJ = 0
        aux[0].CountJ = 1

        res = self.Module.RequestParam(devInd, aux);
        if (res[0] == False):
            return False
        else:
            count = 0
            auxVal = []
            for i in range(0, res[1][0].Size // 4):
                auxVal.append(0)
            for i in range(0, aux[0].CountI):
                for j in range(0, res[1][0].Size // 4):
                    auxVal[j] = res[1][0].Values[count]
                    count += 1
                self.ChInfo[devInd][i + chOffset].Unit = self.__IntToStr(auxVal)

        # Channel Low Limit
        if (chType == LDTP_Const.LDTP_CHTYPE_ANIN):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_ANIN_LOWLIM
        elif (chType == LDTP_Const.LDTP_CHTYPE_PULSE):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_PULSE_LOWLIM
        elif (chType == LDTP_Const.LDTP_CHTYPE_NAV):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_NAV_LOWLIM
        elif (chType == LDTP_Const.LDTP_CHTYPE_CALC):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_CALC_LOWLIM
        elif (chType == LDTP_Const.LDTP_CHTYPE_ANOUT):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_ANOUT_LOWLIM
        elif (chType == LDTP_Const.LDTP_CHTYPE_INTERN):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_INT_LOWLIM
        elif (chType == LDTP_Const.LDTP_CHTYPE_EXTAN):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_EXTAN_LOWLIM

        aux[0].Size = 4
        aux[0].IndexI = 0
        aux[0].CountI = numCh
        aux[0].IndexJ = 0
        aux[0].CountJ = 1

        res = self.Module.RequestParam(devInd, aux);
        if (res[0] == False):
            return False
        else:
            for i in range(0, aux[0].CountI):
                self.ChInfo[devInd][i + chOffset].HighLim = self.__IntToFloat32(res[1][0].Values[i])

        # Channel High Limit
        if (chType == LDTP_Const.LDTP_CHTYPE_ANIN):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_ANIN_HIGHLIM
        elif (chType == LDTP_Const.LDTP_CHTYPE_PULSE):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_PULSE_HIGHLIM
        elif (chType == LDTP_Const.LDTP_CHTYPE_NAV):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_NAV_HIGHLIM
        elif (chType == LDTP_Const.LDTP_CHTYPE_CALC):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_CALC_HIGHLIM
        elif (chType == LDTP_Const.LDTP_CHTYPE_ANOUT):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_ANOUT_HIGHLIM
        elif (chType == LDTP_Const.LDTP_CHTYPE_INTERN):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_INT_HIGHLIM
        elif (chType == LDTP_Const.LDTP_CHTYPE_EXTAN):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_EXTAN_HIGHLIM
            
        aux[0].Size = 4
        aux[0].IndexI = 0
        aux[0].CountI = numCh
        aux[0].IndexJ = 0
        aux[0].CountJ = 1

        res = self.Module.RequestParam(devInd, aux);
        if (res[0] == False):
            return False
        else:
            for i in range(0, aux[0].CountI):
                self.ChInfo[devInd][i + chOffset].LowLim = self.__IntToFloat32(res[1][0].Values[i])

        for i in range(0, aux[0].CountI):
            self.ChInfo[devInd][i + chOffset].ChIndex = i + (chType << 10)
            self.ChInfo[devInd][i + chOffset].IsDig = False
            if (chType == LDTP_Const.LDTP_CHTYPE_ANIN):
                self.ChInfo[devInd][i + chOffset].coefAng = (self.ChInfo[devInd][i + chOffset].HighLim - self.ChInfo[devInd][i + chOffset].LowLim) / \
                                                (LDTP_Const.LDTP_ANIN_RANGE_NOT_OVERRANGE)
                self.ChInfo[devInd][i + chOffset].coefLin = self.ChInfo[devInd][i + chOffset].HighLim - \
                                            (self.ChInfo[devInd][i + chOffset].coefAng * (LDTP_Const.LDTP_ANIN_RANGE_NOT_OVERRANGE / 2))
            else:
                self.ChInfo[devInd][i + chOffset].coefAng = (self.ChInfo[devInd][i + chOffset].HighLim - self.ChInfo[devInd][i + chOffset].LowLim) / \
                                                (LDTP_Const.LDTP_ANIN_RANGE)
                self.ChInfo[devInd][i + chOffset].coefLin = self.ChInfo[devInd][i + chOffset].HighLim - \
                                            (self.ChInfo[devInd][i + chOffset].coefAng * (LDTP_Const.LDTP_ANIN_RANGE / 2))

        return True

    # ------------------------------------------------------------------
    def __GetDigChannelConf(self, devInd, chType):

        if (chType == LDTP_Const.LDTP_CHTYPE_DIGIN):
            numCh = self.Module.GetDevInfo(devInd).NumDigInCh
        elif (chType == LDTP_Const.LDTP_CHTYPE_DIGOUT):
            numCh = self.Module.GetDevInfo(devInd).NumDigOutCh
        elif (chType == LDTP_Const.LDTP_CHTYPE_EXTDIG):
            numCh = self.Module.GetDevInfo(devInd).NumExtDigCh
        else:
            print('__GetDigChannelConf: Invalid ChType')
            return False

        chOffset = len(self.ChInfo[devInd])

        # Num bits per channel
        aux = []
        aux.append(LDTP_Module.Param_Data())
        if (chType == LDTP_Const.LDTP_CHTYPE_DIGIN):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_NBITSDI
        elif (chType == LDTP_Const.LDTP_CHTYPE_DIGOUT):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_NBITSDO
        elif (chType == LDTP_Const.LDTP_CHTYPE_EXTDIG):
            aux[0].ParamNum = LDTP_Const.LDTP_PARAM_NBITSEXTDIG
            
        aux[0].Size = 4
        aux[0].IndexI = 0
        aux[0].CountI = numCh
        aux[0].IndexJ = 0
        aux[0].CountJ = 1

        res = self.Module.RequestParam(devInd, aux);
        if (res[0] == False):
            return False
        else:
            count = 0
            auxVal = []
            for i in range(0, aux[0].CountI):
                self.ChInfo[devInd].append(LDTP_Module.ChInfo())
                self.ChInfo[devInd][i + chOffset].NumBits = res[1][0].Values[i]
                self.ChInfo[devInd][i + chOffset].BitName = []
                self.ChInfo[devInd][i + chOffset].BitHigh = []
                self.ChInfo[devInd][i + chOffset].BitLow = []
        

        # Channel name
        for iCh in range(0, numCh):
            if (chType == LDTP_Const.LDTP_CHTYPE_DIGIN):
                aux[0].ParamNum = LDTP_Const.LDTP_PARAM_DIGIN_CHNAME
            elif (chType == LDTP_Const.LDTP_CHTYPE_DIGOUT):
                aux[0].ParamNum = LDTP_Const.LDTP_PARAM_DIGOUT_CHNAME
            elif (chType == LDTP_Const.LDTP_CHTYPE_EXTDIG):
                aux[0].ParamNum = LDTP_Const.LDTP_PARAM_EXTDIG_CHNAME
        
            aux[0].Size = 32
            aux[0].IndexI = iCh
            aux[0].CountI = 1
            aux[0].IndexJ = 0
            aux[0].CountJ = self.ChInfo[devInd][iCh + chOffset].NumBits

            res = self.Module.RequestParam(devInd, aux);
            if (res[0] == False):
                return False
            else:
                count = 0
                auxVal = []
                for i in range(0, math.ceil(res[1][0].Size / 4)):
                    auxVal.append(0)
                for i in range(0, aux[0].CountJ):
                    for j in range(0, math.ceil(res[1][0].Size / 4)):
                        auxVal[j] = res[1][0].Values[count]
                        count += 1
                    self.ChInfo[devInd][iCh + chOffset].BitName.append(self.__IntToStr(auxVal))

        # Channel High Val
        for iCh in range(0, numCh):
            if (chType == LDTP_Const.LDTP_CHTYPE_DIGIN):
                aux[0].ParamNum = LDTP_Const.LDTP_PARAM_DIGIN_VALHIGH
            elif (chType == LDTP_Const.LDTP_CHTYPE_DIGOUT):
                aux[0].ParamNum = LDTP_Const.LDTP_PARAM_DIGOUT_VALHIGH
            elif (chType == LDTP_Const.LDTP_CHTYPE_EXTDIG):
                aux[0].ParamNum = LDTP_Const.LDTP_PARAM_EXTDIG_VALHIGH
        
            aux[0].Size = 32
            aux[0].IndexI = iCh
            aux[0].CountI = 1
            aux[0].IndexJ = 0
            aux[0].CountJ = self.ChInfo[devInd][iCh + chOffset].NumBits

            res = self.Module.RequestParam(devInd, aux);
            if (res[0] == False):
                return False
            else:
                count = 0
                auxVal = []
                for i in range(0, math.ceil(res[1][0].Size / 4)):
                    auxVal.append(0)
                for i in range(0, aux[0].CountJ):
                    for j in range(0, math.ceil(res[1][0].Size / 4)):
                        auxVal[j] = res[1][0].Values[count]
                        count += 1
                    self.ChInfo[devInd][iCh + chOffset].BitHigh.append(self.__IntToStr(auxVal))

        # Channel Low Val
        for iCh in range(0, numCh):
            if (chType == LDTP_Const.LDTP_CHTYPE_DIGIN):
                aux[0].ParamNum = LDTP_Const.LDTP_PARAM_DIGIN_VALLOW
            elif (chType == LDTP_Const.LDTP_CHTYPE_DIGOUT):
                aux[0].ParamNum = LDTP_Const.LDTP_PARAM_DIGOUT_VALLOW
            elif (chType == LDTP_Const.LDTP_CHTYPE_EXTDIG):
                aux[0].ParamNum = LDTP_Const.LDTP_PARAM_EXTDIG_VALLOW
        
            aux[0].Size = 32
            aux[0].IndexI = iCh
            aux[0].CountI = 1
            aux[0].IndexJ = 0
            aux[0].CountJ = self.ChInfo[devInd][iCh + chOffset].NumBits

            res = self.Module.RequestParam(devInd, aux);
            if (res[0] == False):
                return False
            else:
                count = 0
                auxVal = []
                for i in range(0, math.ceil(res[1][0].Size / 4)):
                    auxVal.append(0)
                for i in range(0, aux[0].CountI):
                    for j in range(0, math.ceil(res[1][0].Size / 4)):
                        auxVal[j] = res[1][0].Values[count]
                        count += 1
                    self.ChInfo[devInd][iCh + chOffset].BitLow.append(self.__IntToStr(auxVal))


        for i in range(0, numCh):
            self.ChInfo[devInd][i + chOffset].ChIndex = i + (chType << 10)
            self.ChInfo[devInd][i + chOffset].IsDig = True
            self.ChInfo[devInd][i + chOffset].coefAng = 1.0
            self.ChInfo[devInd][i + chOffset].coefLin = 0.0
        return True

    # ------------------------------------------------------------------
    def __GetSampFreqOpt(self, devInd):

        # number of sample frequencies available
        aux = []
        aux.append(LDTP_Module.Param_Data())
        aux[0].ParamNum = LDTP_Const.LDTP_PARAM_SAMPFREQNUMOPT
        aux[0].Size = 4
        aux[0].IndexI = 0
        aux[0].CountI = 1
        aux[0].IndexJ = 0
        aux[0].CountJ = 1

        res = self.Module.RequestParam(devInd, aux);
        if (res[0] == False):
            return False
        else:
            count = 0
            while(len(self.__sampFreqNumOpt) <= devInd):
                self.__sampFreqNumOpt.append(0)
            self.__sampFreqNumOpt[devInd] = res[1][0].Values[0]
                
        # sample frequencies available
        aux[0].ParamNum = LDTP_Const.LDTP_PARAM_SAMPFREQOPT
        aux[0].Size = 4
        aux[0].IndexI = 0
        aux[0].CountI = self.__sampFreqNumOpt[devInd]
        aux[0].IndexJ = 0
        aux[0].CountJ = 1

        res = self.Module.RequestParam(devInd, aux);
        if (res[0] == False):
            return False
        else:
            count = 0
            while(len(self.__sampFreqOpt) <= devInd):
                self.__sampFreqOpt.append([])
            self.__sampFreqOpt[devInd] = []
            for i in range(0, res[1][0].CountI):
                self.__sampFreqOpt[devInd].append(self.__IntToFloat32(res[1][0].Values[i]))

        return True


    # ------------------------------------------------------------------
    def SetDigOut(self, deviceIp, digOutNumber, mask, val):
        """ Configure the digital output 

        This function configures the digital output of the device.
        For the "mask" and "val" parameters, each output is indicated by a sequencial bit, starting from the least significant bit.

        Parameters
        ----------            
        deviceIp: The device to configure
        digOutNumber: The index of the digital output, starting from 0 (most devices have only one output)
        mask: If the bit is 1, the output will change to the value of the corresponding bit in "val".
        val: Indicate if the output will go high (1) or low (0). If the corresponding "mask" bit is 0, then the output will not change
            
        Return
        ------
            True if the command was sent correctly
        """

        iDev = -1
        for iDev in range(0, len(self.__listIp)):
            if (deviceIp == self.__listIp[iDev]):
                args = [digOutNumber, mask, val]
                res = self.Module.ExecuteFunction(iDev, True, LDTP_Const.LDTP_MSG_EXECFUNC_CODE_DIG_OUT_ACT, args)
                if (res[0] == False):
                    print('SetDigOut: Error sending command to ' + str(self.__listIp[iDev]))
                    return False
                else:
                    return True
        print('SetDigOut: IP not found: ' + str(deviceIp))
        return True
    
    # ------------------------------------------------------------------
    def SetAnOutV(self, deviceIp, dcVal, acVal, freq):
        """ Configure the analog output to generate voltage

        This function configures the analog output to operate in voltage mode.
        If the acVal is above zero, output generates a sine wave of [acVal] Vpeak and [freq] Hz frequency.

        Parameters
        ----------            
        deviceIp: The device to configure
        dcVal: The dc value of the analog output, in volts
        acVal: The peak value of the analog output, in volts
        freq: Frequency of the sine wave
            
        Return
        ------
            True if the command was sent correctly
        """

        iDev = -1
        for iDev in range(0, len(self.__listIp)):
            if (deviceIp == self.__listIp[iDev]):
                params = []

                # AnOut voltage/current
                params.append(LDTP_Module.Param_Data())
                params[0].ParamNum = 6000
                params[0].IndexI = 0
                params[0].IndexJ = 0
                params[0].CountI = 1
                params[0].CountJ = 1
                params[0].Size = 1
                params[0].Values.append(0) # voltage

                # AnOut DC val
                params.append(LDTP_Module.Param_Data())
                params[1].ParamNum = 6001
                params[1].IndexI = 0
                params[1].IndexJ = 0
                params[1].CountI = 1
                params[1].CountJ = 1
                params[1].Size = 4
                params[1].Values.append(struct.unpack('I', struct.pack('f', dcVal))[0]) # voltage in V

                # AnOut AC val
                params.append(LDTP_Module.Param_Data())
                params[2].ParamNum = 6002
                params[2].IndexI = 0
                params[2].IndexJ = 0
                params[2].CountI = 1
                params[2].CountJ = 1
                params[2].Size = 4
                params[2].Values.append(struct.unpack('I', struct.pack('f', acVal))[0]) # voltage in Vpeak

                # AnOut freq
                params.append(LDTP_Module.Param_Data())
                params[3].ParamNum = 6005
                params[3].IndexI = 0
                params[3].IndexJ = 0
                params[3].CountI = 1
                params[3].CountJ = 1
                params[3].Size = 4
                params[3].Values.append(struct.unpack('I', struct.pack('f', freq))[0]) # frequency in Hz

                # AnOut Mode
                params.append(LDTP_Module.Param_Data())
                params[4].ParamNum = 6008
                params[4].IndexI = 0
                params[4].IndexJ = 0
                params[4].CountI = 1
                params[4].CountJ = 1
                params[4].Size = 1
                params[4].Values.append(0) # sin

                res = self.Module.SetParam(iDev, params)

                # turn on the AC generator
                args = [(LDTP_Const.LDTP_CHTYPE_ANOUT << 10) + 0]
                if (acVal > 0.00001):
                    self.Module.ExecuteFunction(iDev, True, LDTP_Const.LDTP_MSG_EXECFUNC_CODE_AN_OUT_ACT, args)
                else:
                    self.Module.ExecuteFunction(iDev, False, LDTP_Const.LDTP_MSG_EXECFUNC_CODE_AN_OUT_ACT, args)

                if (res == False):
                    print('SetAnOutV: Error sending command to ' + str(self.__listIp[iDev]))
                    return False
                else:
                    return True
        print('SetAnOutV: IP not found: ' + str(deviceIp))
        return True

    # ------------------------------------------------------------------
    def __IntToStr(self, val):
        bytearr = val[0].to_bytes(4, 'little')
        for i in range(1, len(val)):
            bytearr = bytearr + val[i].to_bytes(4, 'little')
        #print(bytearr)
        stringOut = '';
        for i in range(0, len(bytearr)):
            if (bytearr[i] == 0):
                return stringOut
            
            #stringOut += bytearr[i].to_bytes(1, 'little').decode('utf-8');
            stringOut += bytearr[i].to_bytes(1, 'little').decode('ISO-8859–1');
            
        
        return stringOut

    # ------------------------------------------------------------------
    def __IntToFloat32(self, val):
        return (struct.unpack('<f', struct.pack('<I', val)))[0]
        
            
