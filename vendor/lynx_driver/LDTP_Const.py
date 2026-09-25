import collections
import struct

LDTP_CHTYPE_ANIN = 0
LDTP_CHTYPE_PULSE = 1
LDTP_CHTYPE_DIGIN = 2
LDTP_CHTYPE_NAV = 3
LDTP_CHTYPE_CALC = 4
LDTP_CHTYPE_ANOUT = 5
LDTP_CHTYPE_DIGOUT = 6
LDTP_CHTYPE_INTERN = 7
LDTP_CHTYPE_EXTAN = 8
LDTP_CHTYPE_EXTDIG = 9

LDTP_ANIN_RANGE = 4294967295.0
LDTP_ANIN_RANGE_NOT_OVERRANGE = 3932160000.0

LDTP_SYNC_EXT = 0
LDTP_SYNC_GPS = 1
LDTP_SYNC_PTP = 2
LDTP_SYNC_INT = 3

LDTP_STATUS_SYS_READY     = 0
LDTP_STATUS_SYS_BUSY      = 1
LDTP_STATUS_SYS_OPERROR   = 2
LDTP_STATUS_SYS_FATAL_ERR = 3

LDTP_MSG_PROTOCOL = 1
LDTP_MSG_COMMAND_PORT = 44001

LDTP_MSG_EXECFUNC_QUERY = 0
LDTP_MSG_EXECFUNC_START = 1
LDTP_MSG_EXECFUNC_STOP  = 2

LDTP_MSG_EXECFUNC_CODE_AN_OUT_ACT = 1601
LDTP_MSG_EXECFUNC_CODE_DIG_OUT_ACT = 1701

LDTP_MSG_PACKCODE_IDREQUEST          = 0x000C
LDTP_MSG_PACKCODE_SETSYNC            = 0x0001
LDTP_MSG_PACKCODE_SETPARAM           = 0x0002
LDTP_MSG_PACKCODE_REQUESTPARAM       = 0x0004
LDTP_MSG_PACKCODE_PARAMDATA          = 0x0005
LDTP_MSG_PACKCODE_DATACONNREQUEST    = 0x0006
LDTP_MSG_PACKCODE_DATACONNRELEASE    = 0x0008
LDTP_MSG_PACKCODE_STATUSREQUEST      = 0x000A
LDTP_MSG_PACKCODE_STATUSDATA         = 0x000B
LDTP_MSG_PACKCODE_IDDATA             = 0x000D
LDTP_MSG_PACKCODE_EXECFUNC           = 0x000E
LDTP_MSG_PACKCODE_DATAACQSETUP       = 0x1000
LDTP_MSG_PACKCODE_STARTACQ           = 0x1002
LDTP_MSG_PACKCODE_STOPACQ            = 0x1004
LDTP_MSG_PACKCODE_KEEPALIVE          = 0x1006
LDTP_MSG_PACKCODE_PLAYBACK           = 0x1008
LDTP_MSG_PACKCODE_DATAABORT          = 0x100B
LDTP_MSG_PACKCODE_ACK                = 0x100F
LDTP_MSG_PACKCODE_DATAPACKET         = 0x100D

LDTP_MSG_ACKTYPE_GENERIC         = 1000
LDTP_MSG_ACKTYPE_ACQSETUP        = 1010
LDTP_MSG_ACKTYPE_EXECFUNC        = 1020
LDTP_MSG_ACKTYPE_SETPARAM        = 1030
LDTP_MSG_ACKTYPE_SETSYNC         = 1040
LDTP_MSG_ACKTYPE_DATACONNREQUEST = 1050
LDTP_MSG_ACKTYPE_DATACONNRELEASE = 1060
LDTP_MSG_ACKTYPE_PLAYBACKDATA    = 1070
LDTP_MSG_ACKTYPE_STARTACQ        = 1080
LDTP_MSG_ACKTYPE_STOPACQ         = 1090
LDTP_MSG_ACKTYPE_SETADDR         = 1200

# Parameters
LDTP_PARAM_NBITSDI                = 70
LDTP_PARAM_NBITSDO                = 71
LDTP_PARAM_NBITSEXTDIG            = 72

LDTP_PARAM_SAMPFREQOPT            = 501
LDTP_PARAM_SAMPFREQNUMOPT         = 502

LDTP_PARAM_ANIN_CHNAME            = 1901
LDTP_PARAM_ANIN_UNIT              = 1902
LDTP_PARAM_ANIN_LOWLIM            = 1921
LDTP_PARAM_ANIN_HIGHLIM           = 1922
LDTP_PARAM_ANIN_CHCAP             = 1931

LDTP_PARAM_PULSE_CHNAME           = 2901
LDTP_PARAM_PULSE_UNIT             = 2902
LDTP_PARAM_PULSE_LOWLIM           = 2921
LDTP_PARAM_PULSE_HIGHLIM          = 2922
LDTP_PARAM_PULSE_CHCAP            = 2931

LDTP_PARAM_DIGIN_CHNAME           = 3901
LDTP_PARAM_DIGIN_VALLOW           = 3921
LDTP_PARAM_DIGIN_VALHIGH          = 3922
LDTP_PARAM_DIGIN_CHCAP            = 3931

LDTP_PARAM_NAV_CHNAME             = 4901
LDTP_PARAM_NAV_UNIT               = 4902
LDTP_PARAM_NAV_LOWLIM             = 4921
LDTP_PARAM_NAV_HIGHLIM            = 4922
LDTP_PARAM_NAV_CHCAP              = 4931

LDTP_PARAM_CALC_CHNAME            = 5901
LDTP_PARAM_CALC_UNIT              = 5902
LDTP_PARAM_CALC_LOWLIM            = 5921
LDTP_PARAM_CALC_HIGHLIM           = 5922
LDTP_PARAM_CALC_CHCAP             = 5931

LDTP_PARAM_ANOUT_CHNAME           = 6901
LDTP_PARAM_ANOUT_UNIT             = 6902
LDTP_PARAM_ANOUT_LOWLIM           = 6921
LDTP_PARAM_ANOUT_HIGHLIM          = 6922
LDTP_PARAM_ANOUT_CHCAP            = 6931

LDTP_PARAM_DIGOUT_CHNAME          = 7901
LDTP_PARAM_DIGOUT_VALLOW          = 7921
LDTP_PARAM_DIGOUT_VALHIGH         = 7922
LDTP_PARAM_DIGOUT_CHCAP           = 7931

LDTP_PARAM_INT_CHNAME             = 8901
LDTP_PARAM_INT_UNIT               = 8902
LDTP_PARAM_INT_LOWLIM             = 8921
LDTP_PARAM_INT_HIGHLIM            = 8922
LDTP_PARAM_INT_CHCAP              = 8931

LDTP_PARAM_EXTAN_CHNAME           = 9901
LDTP_PARAM_EXTAN_UNIT             = 9902
LDTP_PARAM_EXTAN_LOWLIM           = 9921
LDTP_PARAM_EXTAN_HIGHLIM          = 9922
LDTP_PARAM_EXTAN_CHCAP            = 9931

LDTP_PARAM_EXTDIG_CHNAME          = 10901
LDTP_PARAM_EXTDIG_VALLOW          = 10921
LDTP_PARAM_EXTDIG_VALHIGH         = 10922
LDTP_PARAM_EXTODIG_CHCAP           = 10931



# ------------------------------------------------------------------------------
# ------------------------- Packet Messages -------------------------
# ------------------------------------------------------------------------------

# ---------- Packet Generic ----------
LDTP_MSG_PACK_GENERIC_FORMAT = '<HBBH'
LDTP_MSG_PACK_GENERIC_NAMEDTUPLE = ('PacketCode', 'Protocol', 'Domain', 'CommandTag')

ldtp_packet_generic = collections.namedtuple('Packet_Generic', LDTP_MSG_PACK_GENERIC_NAMEDTUPLE)

def ldtp_byte_to_packet_generic(data):
    return ldtp_packet_generic._make(struct.unpack_from(LDTP_MSG_PACK_GENERIC_FORMAT, data))

# ---------- Packet IDRequest ----------
LDTP_MSG_PACK_IDREQUEST_FORMAT = '<HBBHHII'
LDTP_MSG_PACK_IDREQUEST_NAMEDTUPLE = ('PacketCode', 'Protocol', 'Domain', 'CommandTag',
                                                          'Reserved1', 'SerialNumber', 'Reserved3')

ldtp_packet_idrequest = collections.namedtuple('Packet_IDRequest', LDTP_MSG_PACK_IDREQUEST_NAMEDTUPLE)

def ldtp_create_packet_idrequest(command_tag = 0):
    aux = ldtp_packet_idrequest(LDTP_MSG_PACKCODE_IDREQUEST, LDTP_MSG_PROTOCOL, 0, command_tag | 0x8000, 0, 0, 0)
    return aux

def ldtp_packet_to_byte_idrequest(packet):
    return struct.pack(LDTP_MSG_PACK_IDREQUEST_FORMAT, *list(packet))

# ---------- Packet IDData ----------
LDTP_MSG_PACK_IDDATA_FORMAT = '<HBBHHIIIIfffIHHHHHHHHHHHHHHHHHBBHH16s16sHHHHHBBIIIIIIIIIIIIIIHHHHHHHHHHHHHHHHIIIIIIIIIII'
LDTP_MSG_PACK_IDDATA_NAMEDTUPLE = ('PacketCode', 'Protocol', 'Domain', 'CommandTag',
    'SystemStatus', 'DeviceIDLow', 'DeviceIDHigh', 'DeviceIP', 'Timestamp', 'MaxSampleFreq', 'MaxRecordingFreq',
    'MaxPlaybackFreq', 'LockedIP', 'TotalChannelNum', 'Port', 'NumAnInCh', 'NumPulseCh', 'NumDigInCh', 'NumNavCh',
    'NumAnOutCh', 'NumDigOutCh', 'NumRecCh', 'NumCalcCh', 'NumExtAnCh', 'NumExtDigCh', 'NumIntCh', 'Reserved1',
    'Reserved2', 'Reserved3', 'Reserved4', 'SyncSetup', 'DevFormatCap', 'DevType', 'DevCap', 'DevModel', 'DevTag',
    'VersionHW', 'VersionPLD', 'VersionSW1', 'VersionSW2', 'LoaderVersion', 'LoaderError', 'LoaderStatus', 'HWFuncComp',
    'PLDFuncComp', 'SW1FuncComp', 'SW2FuncComp', 'AppIDLo', 'AppIDMidLo', 'AppIDMidHi', 'AppIDHi', 'LastCalibDate',
    'LastServiceDate', 'LastPowerOnDate', 'LastSWUpdate', 'LastOpErrorDate', 'LastFatalErrorDate', 'HWExpXVersion',
    'PLDExpXVersion', 'SWExpXVersion', 'ModelExpX', 'HWExpYVersion', 'PLDExpYVersion', 'SWExpYVersion', 'ModelExpY',
    'HWExpZVersion', 'PLDExpZVersion', 'SWExpZVersion', 'ModelExpZ', 'HWExpTVersion', 'PLDExpTVersion', 'SWExpTVersion',
    'ModelExpT', 'Reserved5', 'Reserved6', 'Reserved7', 'Reserved8', 'Reserved9', 'Reserved10', 'Reserved11', 'Reserved12',
    'Reserved13', 'Reserved14', 'Reserved15')

ldtp_packet_iddata = collections.namedtuple('Packet_IDData', LDTP_MSG_PACK_IDDATA_NAMEDTUPLE)

def ldtp_byte_to_packet_iddata(data):
    return ldtp_packet_iddata._make(struct.unpack_from(LDTP_MSG_PACK_IDDATA_FORMAT, data))

# ---------- Packet ExecuteFunction ----------
LDTP_MSG_PACK_EXECFUNC_FORMAT = '<HBBHBBI'
LDTP_MSG_PACK_EXECFUNC_NAMEDTUPLE = ('PacketCode', 'Protocol', 'Domain', 'CommandTag',
    'NumberOfArguments', 'Action', 'FunctionNumber', 'FunctionArgument')

ldtp_packet_execfunc = collections.namedtuple('Packet_ExecFunc', LDTP_MSG_PACK_EXECFUNC_NAMEDTUPLE)

def ldtp_create_packet_execfunc_start(funcNum, args, command_tag):
    aux = ldtp_packet_execfunc(LDTP_MSG_PACKCODE_EXECFUNC, LDTP_MSG_PROTOCOL, 0, command_tag | 0x8000,
                                len(args), LDTP_MSG_EXECFUNC_START, funcNum, args)
    return aux

def ldtp_create_packet_execfunc_stop(funcNum, args, command_tag):
    aux = ldtp_packet_execfunc(LDTP_MSG_PACKCODE_EXECFUNC, LDTP_MSG_PROTOCOL, 0, command_tag | 0x8000,
                                len(args), LDTP_MSG_EXECFUNC_STOP, funcNum, args)
    return aux

def ldtp_packet_to_byte_execfunc(packet):
    listAux = (packet.PacketCode,)
    for i in range(1, 7):
        listAux = listAux + (packet[i],)
        
    sAux = LDTP_MSG_PACK_EXECFUNC_FORMAT
    if (len(packet.FunctionArgument) > 0):
        for i in range(len(packet.FunctionArgument)):
            sAux = sAux + 'I'
            listAux = listAux + (packet.FunctionArgument[i],)

    return struct.pack(sAux, *listAux)

# ---------- Packet DataPacket ----------
LDTP_MSG_PACK_DATA_FORMAT = '<HBBHHIfHHBBHII'
LDTP_MSG_PACK_DATA_NAMEDTUPLE = ('PacketCode', 'Protocol', 'Domain', 'CommandTag',
    'SystemStatus', 'FrameNumber', 'SampleFreq', 'TotalChNumber', 'SamplesPerChannel', 'DataFlags',
    'Specific', 'Event_SlowData', 'TimestampSs', 'TimestampS')

ldtp_packet_data = collections.namedtuple('Packet_Data', LDTP_MSG_PACK_DATA_NAMEDTUPLE)

def ldtp_byte_to_packet_data(data):
    return ldtp_packet_data._make(struct.unpack_from(LDTP_MSG_PACK_DATA_FORMAT, data))

def ldtp_get_samples_from_packet(data):
    samples = (int.from_bytes(data[8*4:(8*4)+4], byteorder='little', signed=True),)
    for i in range(9, len(data)//4):
        samples = samples + (int.from_bytes(data[i*4:(i*4)+4], byteorder='little', signed=True),)
    return samples

# ---------- Packet StartAcq ----------
LDTP_MSG_PACK_STARTACQ_FORMAT = '<HBBHHIIIIII'
LDTP_MSG_PACK_STARTACQ_NAMEDTUPLE = ('PacketCode', 'Protocol', 'Domain', 'CommandTag',
    'ConnectionKey', 'StartFlag', 'StartTimeNs', 'StartTimeS', 'Reserved1', 'Reserved2', 'Reserved3')

ldtp_packet_startacq = collections.namedtuple('Packet_StartAcq', LDTP_MSG_PACK_STARTACQ_NAMEDTUPLE)

def ldtp_create_packet_startacq(connectionKey, startTime, command_tag = 0):
    aux = ldtp_packet_startacq(LDTP_MSG_PACKCODE_STARTACQ, LDTP_MSG_PROTOCOL, 0, command_tag | 0x8000, connectionKey, 0x0021,
                               0, startTime, 0, 0, 0)
    return aux

def ldtp_packet_to_byte_startacq(packet):
    return struct.pack(LDTP_MSG_PACK_STARTACQ_FORMAT, *list(packet))

# ---------- Packet StopAcq ----------
LDTP_MSG_PACK_STOPACQ_FORMAT = '<HBBHHIIIIII'
LDTP_MSG_PACK_STOPACQ_NAMEDTUPLE = ('PacketCode', 'Protocol', 'Domain', 'CommandTag',
    'ConnectionKey', 'StopFlag', 'StopTimeNs', 'StopTimeS', 'Reserved1', 'Reserved2', 'Reserved3')

ldtp_packet_stopacq = collections.namedtuple('Packet_StopAcq', LDTP_MSG_PACK_STARTACQ_NAMEDTUPLE)

def ldtp_create_packet_stopacq(connectionKey, command_tag = 0):
    aux = ldtp_packet_stopacq(LDTP_MSG_PACKCODE_STOPACQ, LDTP_MSG_PROTOCOL, 0, command_tag | 0x8000, connectionKey, 0x0001, 0, 0, 0, 0, 0)
    return aux

def ldtp_packet_to_byte_stopacq(packet):
    return struct.pack(LDTP_MSG_PACK_STOPACQ_FORMAT, *list(packet))

# ---------- Packet StatusRequest ----------
LDTP_MSG_PACK_STATUSREQUEST_FORMAT = '<HBBHHBBHI'
LDTP_MSG_PACK_STATUSREQUEST_NAMEDTUPLE = ('PacketCode', 'Protocol', 'Domain', 'CommandTag',
    'ConnectionKey', 'Action', 'Reserved1', 'Reserved2', 'Reserved3')

ldtp_packet_statusrequest = collections.namedtuple('Packet_StatusRequest', LDTP_MSG_PACK_STATUSREQUEST_NAMEDTUPLE)

def ldtp_create_packet_statusrequest(command_tag = 0):
    aux = ldtp_packet_statusrequest(LDTP_MSG_PACKCODE_STATUSREQUEST, LDTP_MSG_PROTOCOL, 0, command_tag | 0x8000, 0, 0, 0, 0, 0)
    return aux

def ldtp_packet_to_byte_statusrequest(packet):
    return struct.pack(LDTP_MSG_PACK_STATUSREQUEST_FORMAT, *list(packet))

# ---------- Packet StatusData ----------
LDTP_MSG_PACK_STATUSDATA_FORMAT = '<HBBHHIfHHBBHIIIIIIIffHBB'
LDTP_MSG_PACK_STATUSDATA_NAMEDTUPLE = ('PacketCode', 'Protocol', 'Domain', 'CommandTag',
    'SystemStatus', 'SyncMaster', 'SampleFreq', 'TotalChNumber', 'SamplesPerChannel', 'DataFlags',
    'SyncSetup', 'SlowData', 'TimestampSs', 'TimestampS', 'DeviceIDLow', 'DeviceIDHigh', 'LockedIP',
    'LastStartTimeNs', 'LastStartTimeS', 'RecordingFreq', 'PlaybackFreq', 'NumberOfSignals', 'Action',
    'Reserved')

ldtp_packet_statusdata = collections.namedtuple('Packet_StatusData', LDTP_MSG_PACK_STATUSDATA_NAMEDTUPLE)

def ldtp_byte_to_packet_statusdata(data):
    return ldtp_packet_statusdata._make(struct.unpack_from(LDTP_MSG_PACK_STATUSDATA_FORMAT, data))

# ---------- Packet DataConnRequest ----------
LDTP_MSG_PACK_DATACONNREQUEST_FORMAT = '<HBBHHII'
LDTP_MSG_PACK_DATACONNREQUEST_NAMEDTUPLE = ('PacketCode', 'Protocol', 'Domain', 'CommandTag',
    'RequestedConnection', 'Reserved1', 'Reserved2')

ldtp_packet_dataconnrequest = collections.namedtuple('Packet_DataConnRequest', LDTP_MSG_PACK_DATACONNREQUEST_NAMEDTUPLE)

def ldtp_create_packet_dataconnrequest(command_tag = 0):
    aux = ldtp_packet_dataconnrequest(LDTP_MSG_PACKCODE_DATACONNREQUEST, LDTP_MSG_PROTOCOL, 0, command_tag | 0x8000, 0, 0, 0)
    return aux

def ldtp_packet_to_byte_dataconnrequest(packet):
    return struct.pack(LDTP_MSG_PACK_DATACONNREQUEST_FORMAT, *list(packet))

# ---------- Packet DataConnRelease ----------
LDTP_MSG_PACK_DATACONNRELEASE_FORMAT = '<HBBHHII'
LDTP_MSG_PACK_DATACONNRELEASE_NAMEDTUPLE = ('PacketCode', 'Protocol', 'Domain', 'CommandTag',
    'ConnectionKey', 'Reserved1', 'Reserved2')

ldtp_packet_dataconnrelease = collections.namedtuple('Packet_DataConnRelease', LDTP_MSG_PACK_DATACONNRELEASE_NAMEDTUPLE)

def ldtp_create_packet_dataconnrelease(connectionKey, command_tag = 0):
    aux = ldtp_packet_dataconnrelease(LDTP_MSG_PACKCODE_DATACONNRELEASE, LDTP_MSG_PROTOCOL, 0, command_tag | 0x8000, connectionKey, 0, 0)
    return aux

def ldtp_packet_to_byte_dataconnrelease(packet):
    return struct.pack(LDTP_MSG_PACK_DATACONNRELEASE_FORMAT, *list(packet))

# ---------- Packet DataAcqSetup ----------
LDTP_MSG_PACK_DATAACQSETUP_FORMAT = '<HBBHHfHHBBBBIII'
LDTP_MSG_PACK_DATAACQSETUP_NAMEDTUPLE = ('PacketCode', 'Protocol', 'Domain', 'CommandTag',
    'ConnectionKey', 'SampleFreq', 'TotalNumberOfChannels', 'SamplesPerChannel', 'DataSetupFlags', 'DigitalSamples',
    'AcquisitionSetup', 'Reserved1', 'Reserved2', 'Reserved3', 'Reserved4', 'Channels')

ldtp_packet_dataacqsetup = collections.namedtuple('Packet_DataAcqSetup', LDTP_MSG_PACK_DATAACQSETUP_NAMEDTUPLE)

def ldtp_create_packet_dataacqsetup(connectionKey, sampFreq, sampsPerCh, channels, command_tag = 0):
    aux = ldtp_packet_dataacqsetup(LDTP_MSG_PACKCODE_DATAACQSETUP, LDTP_MSG_PROTOCOL, 0, command_tag | 0x8000, connectionKey,
                        sampFreq, len(channels), sampsPerCh, 0x09, 0, 1, 0, 0, 0, 0, channels)
    return aux

def ldtp_packet_to_byte_dataacqsetup(packet):
    listAux = (packet.PacketCode,)
    for i in range(1, 15):
        listAux = listAux + (packet[i],)
        
    sAux = LDTP_MSG_PACK_DATAACQSETUP_FORMAT
    if (len(packet.Channels) > 0):
        for i in range(len(packet.Channels)):
            sAux = sAux + 'H'
            listAux = listAux + (packet.Channels[i],)

    return struct.pack(sAux, *listAux)

# ---------- Packet SetSync ----------
LDTP_MSG_PACK_SETSYNC_FORMAT = '<HBBHBBII'
LDTP_MSG_PACK_SETSYNC_NAMEDTUPLE = ('PacketCode', 'Protocol', 'Domain', 'CommandTag',
    'SyncSetup', 'Stratum', 'TimeSubS', 'TimeS')

ldtp_packet_setsync = collections.namedtuple('Packet_SetSync', LDTP_MSG_PACK_SETSYNC_NAMEDTUPLE)

def ldtp_create_packet_setsync(syncSetup = 0x80, timestampS = 0, timestampSubS = 0, stratum = 0, command_tag = 0):
    aux = ldtp_packet_setsync(LDTP_MSG_PACKCODE_SETSYNC, LDTP_MSG_PROTOCOL, 0, command_tag | 0x8000, syncSetup, stratum, timestampSubS, timestampS)
    return aux

def ldtp_packet_to_byte_setsync(packet):
    return struct.pack(LDTP_MSG_PACK_SETSYNC_FORMAT, *list(packet))

# ---------- Packet KeepAlive ----------
LDTP_MSG_PACK_KEEPALIVE_FORMAT = '<HBBHHII'
LDTP_MSG_PACK_KEEPALIVE_NAMEDTUPLE = ('PacketCode', 'Protocol', 'Domain', 'CommandTag',
    'ConnectionKey', 'Time', 'Reserved1')

ldtp_packet_keepalive = collections.namedtuple('Packet_KeepAlive', LDTP_MSG_PACK_KEEPALIVE_NAMEDTUPLE)

def ldtp_create_packet_keepalive(connectionKey, command_tag = 0):
    aux = ldtp_packet_keepalive(LDTP_MSG_PACKCODE_KEEPALIVE, LDTP_MSG_PROTOCOL, 0, command_tag | 0x8000, connectionKey, 0, 0)
    return aux

def ldtp_packet_to_byte_keepalive(packet):
    return struct.pack(LDTP_MSG_PACK_KEEPALIVE_FORMAT, *list(packet))

# ---------- Packet SetParam ----------
LDTP_MSG_PACK_SETPARAM_FORMAT = '<HBBHHI'
LDTP_MSG_PACK_SETPARAM_NAMEDTUPLE = ('PacketCode', 'Protocol', 'Domain', 'CommandTag',
    'NumberParameters', 'OwnerID', 'ParamData')

ldtp_packet_setparam = collections.namedtuple('Packet_SetParam', LDTP_MSG_PACK_SETPARAM_NAMEDTUPLE)

def ldtp_create_packet_setparam(num_params, param_data, command_tag = 0):
    aux = ldtp_packet_setparam(LDTP_MSG_PACKCODE_SETPARAM, LDTP_MSG_PROTOCOL, 0, command_tag | 0x8000, num_params, 0,
                        param_data)
    return aux

def ldtp_packet_to_byte_setparam(packet):
    listAux = (packet.PacketCode,)
    for i in range(1, 6):
        listAux = listAux + (packet[i],)
        
    sAux = LDTP_MSG_PACK_SETPARAM_FORMAT
    if (len(packet.ParamData) > 0):
        for i in range(len(packet.ParamData)):
            sAux = sAux + 'I'
            listAux = listAux + (packet.ParamData[i],)

    return struct.pack(sAux, *listAux)

# ---------- Packet RequestParam ----------
LDTP_MSG_PACK_REQUESTPARAM_FORMAT = '<HBBHH'
LDTP_MSG_PACK_REQUESTPARAM_NAMEDTUPLE = ('PacketCode', 'Protocol', 'Domain', 'CommandTag',
    'NumberParameters', 'ParamData')

ldtp_packet_requestparam = collections.namedtuple('Packet_RequestParam', LDTP_MSG_PACK_REQUESTPARAM_NAMEDTUPLE)

def ldtp_create_packet_requestparam(param_data, command_tag = 0):
    aux = ldtp_packet_requestparam(LDTP_MSG_PACKCODE_REQUESTPARAM, LDTP_MSG_PROTOCOL, 0, command_tag | 0x8000, len(param_data) // 2,
                        param_data)
    return aux

def ldtp_packet_to_byte_requestparam(packet):
    listAux = (packet.PacketCode,)
    for i in range(1, 5):
        listAux = listAux + (packet[i],)
        
    sAux = LDTP_MSG_PACK_REQUESTPARAM_FORMAT
    if (len(packet.ParamData) > 0):
        for i in range(len(packet.ParamData)):
            sAux = sAux + 'I'
            listAux = listAux + (packet.ParamData[i],)

    return struct.pack(sAux, *listAux)

# ---------- Packet ParamData ----------
LDTP_MSG_PACK_PARAMDATA_FORMAT = '<HBBHHhH'
LDTP_MSG_PACK_PARAMDATA_NAMEDTUPLE = ('PacketCode', 'Protocol', 'Domain', 'CommandTag',
    'NumberParameters', 'ErrorCode', 'ParamNumber')#, 'ParamData')

ldtp_packet_paramdata = collections.namedtuple('Packet_ParamData', LDTP_MSG_PACK_PARAMDATA_NAMEDTUPLE)

def ldtp_byte_to_packet_paramdata(data):
    return ldtp_packet_paramdata._make(struct.unpack_from(LDTP_MSG_PACK_PARAMDATA_FORMAT, data))

def ldtp_get_paramdata_from_packet(data):
    paramData = (int.from_bytes(data[3*4:(3*4)+4], byteorder='little', signed=False),)
    for i in range(4, len(data)//4):
        paramData = paramData + (int.from_bytes(data[i*4:(i*4)+4], byteorder='little', signed=False),)
    return paramData

# ---------- Packet Ack ----------
LDTP_MSG_PACK_ACK_FORMAT = '<HBBHHIIhH'
LDTP_MSG_PACK_ACK_NAMEDTUPLE = ('PacketCode', 'Protocol', 'Domain', 'CommandTag',
    'SystemStatus', 'DeviceIDLow', 'DeviceIDHigh', 'ErrorCode', 'AckType') #, 'Specific')

ldtp_packet_ack = collections.namedtuple('Packet_Ack', LDTP_MSG_PACK_ACK_NAMEDTUPLE)

def ldtp_byte_to_packet_ack(data):
    return ldtp_packet_ack._make(struct.unpack_from(LDTP_MSG_PACK_ACK_FORMAT, data))

def ldtp_get_specific_from_packet(data):
    specific = (int.from_bytes(data[5*4:(5*4)+4], byteorder='little', signed=False),)
    for i in range(6, len(data)//4):
        specific = specific + (int.from_bytes(data[i*4:(i*4)+4], byteorder='little', signed=False),)
    return specific
